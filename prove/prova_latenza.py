import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della latenza vera della voce (06/10, proposte P2, P3, P4 e P11 di
docs/ricerche/2026-10-06-analisi-complessiva.md; P1 è in prova_stt_correzione):

- guardiano caldo: `prepara` carica guardiano e rilevatore di pericolo con un tempo lungo, un
  giudizio scaduto li ricarica in secondo piano (prima un caricamento più lungo del tempo
  massimo si chiudeva a metà a ogni turno: 3 s per ogni frase dei minori sulla DGX), la
  domanda si giudica mentre il modello risponde e nessuna frase esce prima del giudizio;
- conversazione ripresa dopo un riavvio messa in cache (stesso prefisso del primo turno);
- registro dei turni: mediana e p90 per giorno con le cause, avviso oltre la soglia,
  `calliope stato --turni`, tempo di rilettura del prompt dalla prima passata;
- compressione: il riassunto dell'agente che non comincia entro il tempo massimo passa alla
  voce o ai tagli.

Niente rete né modelli: Ollama, backend e riassuntori finti."""

import io
from pathlib import Path
import json
import tempfile
import threading
import time
from contextlib import redirect_stdout
from types import SimpleNamespace

from calliope import guardiano as G
from calliope import latenza
from calliope.brain import Brain
from calliope.compressione import Compressore, RiassuntoreTagli, normalizza
from calliope.config import Config
from calliope.conversazione import Conversazione
from calliope.tools.builtin import build_registry

errori = 0


def verifica(nome, cond, info=""):
    global errori
    errori += not cond
    print(f"{'ok ' if cond else 'ERR'} {nome}" + (f"  {info}" if info and not cond else ""))


# ─────────────────────────── P2: guardiano caldo ───────────────────────────
class ReadTimeout(Exception):
    """Come httpx.ReadTimeout (conta il nome)."""


class OllamaFinto:
    """Un Ollama che carica i modelli: la prima richiesta a un modello scarico costa
    `carico_s`; se il client chiude prima (tempo massimo), il caricamento si perde, come una
    richiesta chiusa a metà (499 nel log di Ollama vero)."""

    def __init__(self, carico_s=0.6, giudizio_s=0.02):
        self.carico_s, self.giudizio_s = carico_s, giudizio_s
        self.caricati: set = set()
        self.richieste: list = []
        self.lock = threading.Lock()

    def post(self, url, json=None, timeout=None):
        modello = json["model"]
        with self.lock:
            self.richieste.append((modello, timeout))
            serve = 0.0 if modello in self.caricati else self.carico_s
        t = float(timeout or 99)
        if serve > t:
            time.sleep(t)
            raise ReadTimeout("caricamento chiuso a metà")
        time.sleep(serve + self.giudizio_s)
        with self.lock:
            self.caricati.add(modello)
        if url.endswith("/api/generate"):
            return SimpleNamespace(status_code=200, json=lambda: {"response": "safe"})
        return SimpleNamespace(status_code=200,
                               json=lambda: {"message": {"content": '{"esito": "NO"}'}})


def cfg_guardiano(**kw):
    c = Config()
    c.guardiano_modello = "llama-guard3:8b"
    c.guardiano_timeout_s = 0.3
    c.llm_backend = "ollama"
    c.llm_model = "gemma4:26b-a4b-it-qat"            # la voce (come sulla DGX)
    c.guardiano_pericolo_modello = "gemma4:e4b-it-qat"   # il rilevatore: un modello suo
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def prova_guardiano():
    print("── guardiano caldo (P2) ──")
    # Prima (05/10): niente prepara del rilevatore e tempo massimo più corto del caricamento.
    # Ogni domanda lo faceva ripartire e lo chiudeva: sempre scaduto
    ol = OllamaFinto(carico_s=0.6)
    g = G.Guardiano(cfg_guardiano(), cliente=ol, log=lambda *a: None)
    ol.caricati.add("llama-guard3:8b")
    esiti = [g.pericolo("ciao", riscalda=False).esito for _ in range(3)]
    verifica("caso della DGX: senza ricarica il rilevatore scade a ogni domanda",
             esiti == [G.GUASTO] * 3 and "gemma4:e4b-it-qat" not in ol.caricati, str(esiti))
    # prepara: guardiano e rilevatore, con il tempo lungo
    ol = OllamaFinto(carico_s=0.6)
    g = G.Guardiano(cfg_guardiano(), cliente=ol, log=lambda *a: None)
    verifica("prepara: il guardiano risponde", g.prepara())
    verifica("prepara: carica anche il rilevatore di pericolo (modello suo)",
             ol.caricati == {"llama-guard3:8b", "gemma4:e4b-it-qat"}, str(ol.caricati))
    verifica("prepara: tempo lungo (AVVIO_S), non quello di un giudizio",
             all(t == G.AVVIO_S for _, t in ol.richieste), str(ol.richieste))
    t0 = time.perf_counter()
    gd = g.giudica_domanda("che ore sono?")
    ms = (time.perf_counter() - t0) * 1000
    verifica("dopo prepara: domanda giudicata subito", gd.esito == G.OK and ms < 250,
             f"{gd.esito} {ms:.0f} ms")
    # Rilevatore scaricato (Ollama l'ha tolto): il primo giudizio scade, la ricarica in
    # secondo piano lo riporta pronto per il turno dopo
    ol.caricati.discard("gemma4:e4b-it-qat")
    p1 = g.pericolo("ciao")
    for _ in range(40):
        if "gemma4:e4b-it-qat" in ol.caricati and not g._riscaldo:
            break
        time.sleep(0.05)
    p2 = g.pericolo("ciao")
    verifica("rilevatore scaricato: scade una volta, si ricarica da solo, poi risponde",
             p1.esito == G.GUASTO and p2.esito == G.OK, f"{p1.esito} → {p2.esito}")
    # Lo stesso per il guardiano
    ol.caricati.discard("llama-guard3:8b")
    g1 = g.giudica("ciao")
    for _ in range(40):
        if "llama-guard3:8b" in ol.caricati and not g._riscaldo:
            break
        time.sleep(0.05)
    verifica("guardiano scaricato: ricaricato in secondo piano",
             g1.esito == G.GUASTO and g.giudica("ciao").esito == G.OK)
    # Una ricarica alla volta per modello
    ol2 = OllamaFinto(carico_s=0.5)
    g2 = G.Guardiano(cfg_guardiano(), cliente=ol2, log=lambda *a: None)
    for _ in range(4):
        g2._riscalda("pericolo")
    time.sleep(0.05)
    n = sum(1 for m, t in ol2.richieste if m == "gemma4:e4b-it-qat")
    verifica("una sola ricarica alla volta", n == 1, str(ol2.richieste))
    # Rilevatore = modello della voce: non lo ricarica il guardiano (lo tiene caldo la voce)
    ol3 = OllamaFinto(carico_s=0.5)
    c3 = cfg_guardiano(guardiano_pericolo_modello="")      # vuoto = il modello della voce
    g3 = G.Guardiano(c3, cliente=ol3, log=lambda *a: None)
    g3.prepara()
    verifica("rilevatore = voce: prepara non lo carica",
             all(m != c3.llm_model for m, _ in ol3.richieste), str(ol3.richieste))
    g3.pericolo("ciao")
    time.sleep(0.1)
    verifica("…e un suo giudizio scaduto non avvia ricariche", not g3._riscaldo
             and sum(1 for m, _ in ol3.richieste if m == c3.llm_model) == 1)

    # In parallelo: la domanda si giudica mentre il modello risponde; nessuna frase esce prima
    class Lento(G.Guardiano):
        def __init__(self):
            super().__init__(cfg_guardiano(), cliente=OllamaFinto(), log=lambda *a: None)
            self.inizio_domanda = None

        def giudica_domanda(self, domanda, categorie_attive=None):
            self.inizio_domanda = time.perf_counter()
            time.sleep(0.3)
            return G.Giudizio(G.OK)

        def giudica(self, domanda, risposta=None, categorie_attive=None, **kw):
            return G.Giudizio(G.OK, ms=1.0)

    gl = Lento()
    uscite = []

    def frasi():
        time.sleep(0.3)                          # il modello impiega 0,3 s per la prima frase
        uscite.append(("generata", time.perf_counter()))
        yield "Uno."
        yield "Due."

    t0 = time.perf_counter()
    out = []
    for f in G.filtra(gl, frasi(), "domanda", True, G.Esito()):
        out.append((f, time.perf_counter() - t0))
    prima = out[0][1]
    verifica("in parallelo: prima frase dopo ~0,3 s (giudizio e risposta insieme), non 0,6",
             out[0][0] == "Uno." and 0.28 <= prima < 0.5, f"{prima:.2f} s")
    verifica("…la domanda si giudica prima che la frase sia generata",
             gl.inizio_domanda is not None and gl.inizio_domanda < uscite[0][1])

    class Pericolo(Lento):
        def giudica_domanda(self, domanda, categorie_attive=None):
            time.sleep(0.2)
            return G.Giudizio(G.PERICOLO, ("autolesionismo",))

    out = list(G.filtra(Pericolo(), iter(["Ecco come fare."]), "d", True, G.Esito()))
    verifica("la frase pronta prima del giudizio non esce: con il pericolo solo la protezione",
             out == [G.PROTEZIONE], str(out))
    gl.close()


# ─────────────────────────── P3: conversazione ripresa in cache ───────────────────────────
class BackendFinto:
    def __init__(self):
        self.scaldati = []

    def warmup(self, messages=None, tools=None):
        self.scaldati.append(([dict(m) for m in messages], tools))
        return {"prompt": 4321}


def brain_finto():
    cfg = Config()
    cfg.llm_num_ctx = 16384
    b = Brain.__new__(Brain)
    b.cfg, b.tools = cfg, build_registry()
    b.backend = BackendFinto()
    b.tool_ctx = None
    return b


def prova_ripresa():
    print("── conversazione ripresa in cache (P3) ──")
    b = brain_finto()
    c = Conversazione("persona:p-dario")
    c.history = [{"role": "user", "content": "Che tempo fa?", "_prov": "voce"},
                 {"role": "assistant", "content": "Sole."}]
    c.riassunto = {"tipo": "compressione", "testo": "Riassunto: il tetto."}
    c.last_turn_at = time.monotonic() - 30
    vecchia = Conversazione("persona:p-bianca")
    vecchia.history = [{"role": "user", "content": "Ciao"}]
    vecchia.last_turn_at = time.monotonic() - 200
    vuota = Conversazione("ospite:x")
    vuota.last_turn_at = time.monotonic()
    righe = []
    res = latenza.scalda_ripresa(b, [vecchia, c, vuota], log=lambda s, **k: righe.append(s))
    msgs, tools = b.backend.scaldati[0]
    sistema = b._system_messages()
    verifica("si scalda la conversazione più recente con della storia (una sola)",
             len(b.backend.scaldati) == 1 and any(m["content"] == "Sole." for m in msgs))
    verifica("prefisso uguale al primo turno: sistema, riassunto, storia, poi la domanda",
             msgs[:len(sistema)] == sistema
             and msgs[len(sistema)]["content"] == "Riassunto: il tetto."
             and msgs[len(sistema) + 1]["content"] == "Che tempo fa?"
             and msgs[-1] == {"role": "user", "content": "ciao"},
             str([m["content"][:20] for m in msgs[-4:]]))
    verifica("stessi tool della risposta vera", tools == b.tools.schemas(online=b.cfg.online))
    verifica("la conversazione corrente di Brain non cambia", b.history == [])
    verifica("riga nel log con turni e token", res and res["token"] == 4321
             and righe and "1 turni" in righe[0] and "4321" in righe[0], str(righe))
    verifica("niente da scaldare: nessuna richiesta",
             latenza.scalda_ripresa(b, [vuota], log=lambda *a, **k: None) is None
             and len(b.backend.scaldati) == 1)
    lunga = Conversazione("persona:p-dario")
    lunga.history = [{"role": "user", "content": "parola " * 40000}]
    lunga.last_turn_at = time.monotonic()
    verifica("storia oltre la finestra: non si scalda (la taglierà il primo turno)",
             b.scalda_conversazione(lunga) is None and len(b.backend.scaldati) == 1)

    class Rotto(BackendFinto):
        def warmup(self, messages=None, tools=None):
            raise ConnectionError("giù")
    b.backend = Rotto()
    righe = []
    verifica("motore giù: nessuna eccezione, una riga",
             latenza.scalda_ripresa(b, [c], log=lambda s, **k: righe.append(s)) is None
             and righe and "non scaldata" in righe[0])


class OllamaRegistra:
    """Un Ollama finto che registra i messaggi come li manderebbe OllamaBackend (_native):
    riscaldamento e prima richiesta di stream_reply, per confrontare i prefissi."""
    def __init__(self):
        from calliope.brain import OllamaBackend
        self._native = OllamaBackend._native
        self.scaldati, self.richieste = [], []

    def warmup(self, messages=None, tools=None):
        self.scaldati.append([self._native(m) for m in messages])
        return {"prompt": 1234}

    def stream(self, messages, tools):
        self.richieste.append([self._native(m) for m in messages])
        yield ("text", "Nel 1873.")


def _uguali_in_testa(a: list, b: list) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def prova_ripresa_con_tool():
    """Q5 dell'analisi del 06/10: con un tool negli ultimi turni il primo turno vero passa da
    _compact_old_results (ora_attuale diventa ora_di_allora, i risultati lunghi si riducono)
    e il prefisso scaldato non era più quello vero: coincideva per 3 messaggi su 9. Ora si
    scalda la storia già compattata come la vedrà il primo turno."""
    print("── conversazione ripresa con tool nella storia (Q5) ──")
    cfg = Config()
    cfg.llm_num_ctx = 16384
    cfg.storia_inattiva_s = 0
    b = Brain(cfg, build_registry(), None)
    b.backend = OllamaRegistra()
    lungo = json.dumps({"ok": True, "trovato": True, "risultati": [
        {"titolo": "Alessandro Manzoni", "testo": "Alessandro Manzoni nacque a Milano. " * 30}],
        "conferma": "Manzoni nacque a Milano nel 1785."}, ensure_ascii=False)
    c = Conversazione("persona:p-dario")
    c.history = [
        {"role": "user", "content": "Che ore sono?", "_prov": "voce"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "name": "ora_attuale", "arguments": {}}]},
        {"role": "tool", "tool_call_id": "c1", "name": "ora_attuale",
         "content": json.dumps({"ora": "10:00", "da_dire": "Sono le 10."})},
        {"role": "assistant", "content": "Sono le 10."},
        {"role": "user", "content": "Chi era Manzoni?", "_prov": "voce"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c2", "name": "biblioteca_cerca", "arguments": {"domanda": "Manzoni"}}]},
        {"role": "tool", "tool_call_id": "c2", "name": "biblioteca_cerca", "content": lungo},
        {"role": "assistant", "content": "Uno scrittore milanese, nato nel 1785."},
        {"role": "user", "content": "E dove è nato?", "_prov": "voce"},
        {"role": "assistant", "content": "A Milano."},
    ]
    c.last_turn_at = time.monotonic() - 30
    res = latenza.scalda_ripresa(b, [c], log=lambda *a, **k: None)
    scaldato = b.backend.scaldati[0][:-1]          # senza il «ciao» finale
    verifica("ripresa con tool: la conversazione salvata non cambia (si scalda una copia)",
             res is not None and json.loads(c.history[2]["content"]).get("ora") == "10:00")
    b.conv = c
    "".join(b.stream_reply("E quando è morto?", "amministra"))
    vera = b.backend.richieste[0]
    n = _uguali_in_testa(scaldato, vera)
    verifica(f"ripresa con tool: il prefisso scaldato è quello del primo turno "
             f"({n} messaggi uguali su {len(scaldato)})", n == len(scaldato),
             str([m.get("content", "")[:40] for m in scaldato[n:n + 1]]
                 + [m.get("content", "")[:40] for m in vera[n:n + 1]]))
    verifica("ripresa con tool: nel prefisso l'ora è «di allora» e il risultato lungo ridotto",
             any("ora_di_allora" in (m.get("content") or "") for m in scaldato)
             and all(len(m.get("content") or "") < 400 for m in scaldato
                     if m.get("role") == "tool"))


# ─────────────────────────── P4: latenza dal registro ───────────────────────────
def turno(giorno, pf, stt=0.2, **kw):
    t = {"inizio": f"{giorno}T10:00:00.000", "esito": "risposta", "prima_frase_s": pf,
         "stt_s": stt}
    t.update(kw)
    return t


def prova_registro():
    print("── latenza dal registro dei turni (P4) ──")
    lenti = ([turno("2026-10-05", 2.5, stt=1.2, stt_correzione_ms=1000.0) for _ in range(6)]
             + [turno("2026-10-05", 4.0, guardiano={"frasi": 1}) for _ in range(3)]
             + [turno("2026-10-05", 1.8, tool=[{"nome": "web_cerca", "ok": True}],
                      lettura_s=3.1) for _ in range(3)]
             + [turno("2026-10-05", 0.9, fine_parlato_s=1.6,
                      contesto={"token": 11000, "finestra": 28672, "percento": 38})
                for _ in range(4)]
             + [{"inizio": "2026-10-05T11:00:00", "esito": "stop"}])
    veloci = [turno("2026-10-02", 0.7 + i / 100) for i in range(12)]
    pochi = [turno("2026-10-04", 3.0) for _ in range(3)]
    g = latenza.per_giorno(veloci + pochi + lenti)
    d = g["2026-10-05"]
    verifica("per giorno, in ordine", list(g) == ["2026-10-02", "2026-10-04", "2026-10-05"])
    verifica("risposte contate (lo stop no)", d["risposte"] == 16 and d["turni"] == 17)
    verifica("mediana e p90 della prima frase",
             d["prima_frase"]["mediana"] == 2.5 and d["prima_frase"]["p90"] == 4.0,
             str(d["prima_frase"]))
    verifica("cause: correzione, guardiano, tool, rilettura lenta",
             d["correzione"]["n"] == 6 and d["correzione"]["ms_mediana"] == 1000.0
             and d["guardiano"]["n"] == 3 and d["tool"]["n"] == 3
             and d["lettura"]["lente"] == 3, json.dumps(d)[:300])
    verifica("base senza tool, guardiano né correzione", d["base"] == {"n": 4, "mediana": 0.9})
    verifica("dalla fine del parlato", d["fine_parlato"]["mediana"] == 1.6)
    a = latenza.avviso(d, 1.2, "2026-10-05")
    verifica("avviso oltre 1,2 s con le cause", a and "2,50 s" in a and "correzione" in a
             and "guardiano" in a and "cache del prefisso persa in 3 turni" in a, str(a))
    verifica("contrario: giorno veloce, nessun avviso", latenza.avviso(g["2026-10-02"]) is None)
    verifica("contrario: lento ma con 3 risposte, nessun avviso",
             latenza.avviso(g["2026-10-04"]) is None)
    t = latenza.testo(g)
    verifica("testo per il terminale: un giorno per riga e l'avviso",
             "2026-10-05  16 risposte  prima frase 2,50 s" in t and "ATTENZIONE" in t
             and t.count("ATTENZIONE") == 1, t)
    # Dal file, all'avvio e da calliope stato --turni
    cartella = tempfile.mkdtemp(prefix="calliope-latenza-")
    with open(os.path.join(cartella, "turni-2026-10-05.jsonl"), "w", encoding="utf-8") as f:
        for x in lenti:
            f.write(json.dumps(x) + "\n")
        f.write("{rotta\n")
    cfg = SimpleNamespace(turn_log_dir=cartella, latenza_avviso_s=1.2)
    import datetime
    verifica("avviso all'avvio: oggi lento", "2,50 s" in (latenza.avviso_recente(
        cfg, datetime.date(2026, 10, 5)) or ""))
    verifica("…anche il giorno dopo (ieri)", latenza.avviso_recente(
        cfg, datetime.date(2026, 10, 6)) is not None)
    verifica("contrario: due giorni dopo niente", latenza.avviso_recente(
        cfg, datetime.date(2026, 10, 8)) is None)
    cfg.latenza_avviso_s = 0
    verifica("contrario: latenza_avviso_s 0 = mai", latenza.avviso_recente(
        cfg, datetime.date(2026, 10, 5)) is None)
    from calliope import stato
    vecchio = stato._config
    cfg_stato = Config()
    cfg_stato.turn_log_dir = cartella
    stato._config = lambda quiet: cfg_stato
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = stato.main(["--turni", "--giorni", "3"])
        uscita = buf.getvalue()
        buf = io.StringIO()
        with redirect_stdout(buf):
            stato.main(["--turni", "--json"])
        js = json.loads(buf.getvalue()[buf.getvalue().index("{"):])
    finally:
        stato._config = vecchio
    verifica("calliope stato --turni", rc == 0 and "2026-10-05  16 risposte" in uscita, uscita)
    verifica("calliope stato --turni --json", js["giorni"]["2026-10-05"]["risposte"] == 16)
    # La rilettura del prompt della prima passata (Ollama: prompt_eval_duration)
    b = brain_finto()
    b.last_lettura_s = None
    b.last_context = None
    b._note_usage({"prompt": 9000, "output": 10, "lettura_ns": 2_800_000_000})
    b._note_usage({"prompt": 9500, "output": 40, "lettura_ns": 150_000_000})
    verifica("lettura_s: quella della prima passata", b.last_lettura_s == 2.8
             and b.last_context["token"] == 9540, str((b.last_lettura_s, b.last_context)))
    b.last_lettura_s = None
    b._note_usage({"prompt": 100, "output": 5})
    verifica("contrario: senza durata (vLLM) niente lettura_s", b.last_lettura_s is None)


# ─────────────────────────── P11: riassunto dell'agente in tempo ───────────────────────────
class ClienteFinto:
    def __init__(self):
        self.interrotti = []

    def interrompi(self, tid=None):
        self.interrotti.append(tid)


class AgenteFinto:
    """Un riassuntore «agente»: `attesa` prima del primo pezzo (la coda dei lavori)."""
    voce = False

    def __init__(self, attesa, nome="agente"):
        self.nome, self.attesa = nome, attesa
        self.cliente = ClienteFinto()

    def riassumi(self, lavoro, controlla=None):
        fine = time.monotonic() + self.attesa
        while time.monotonic() < fine:
            time.sleep(0.01)
        for _ in range(3):                       # i pezzi dello stream
            if controlla is not None:
                controlla()
            time.sleep(0.05)
        return {"dati": normalizza({"argomenti": [f"riassunto di {self.nome}"]}), "token": 9}


def brain_conv():
    b = brain_finto()
    b.conv = Conversazione()
    for i in range(8):
        b.history.append({"role": "user", "content": f"Domanda {i}"})
        b.history.append({"role": "assistant", "content": f"Risposta {i}."})
    b.archivio_conv = None
    return b


def prova_compressione():
    print("── riassunto dell'agente con un tempo massimo (P11) ──")
    cfg = Config()
    cfg.contesto_riassunto_attesa_s = 0.3
    b = brain_conv()
    lento = AgenteFinto(attesa=5.0)
    comp = Compressore(cfg, [lento, RiassuntoreTagli()], None, log=lambda s: None)
    lav = comp.prepara(b)
    t0 = time.monotonic()
    comp._esegui(lav)
    s = time.monotonic() - t0
    verifica("agente in coda oltre il tempo massimo: i tagli, senza aspettarlo",
             lav.usato == "tagli" and s < 1.5 and lav.prove[0].startswith("agente: NonPartito"),
             f"{lav.usato} {s:.2f} s {lav.prove}")
    verifica("…e il suo stream si chiude", lento.cliente.interrotti)
    pronto = AgenteFinto(attesa=0.1)
    comp = Compressore(cfg, [pronto, RiassuntoreTagli()], None, log=lambda s: None)
    lav = comp.prepara(b)
    comp._esegui(lav)
    verifica("contrario: agente che parte in tempo scrive lui il riassunto",
             lav.usato == "agente" and not pronto.cliente.interrotti, str(lav.prove))

    class Lungo(AgenteFinto):
        def riassumi(self, lavoro, controlla=None):
            controlla()                          # primo pezzo subito
            time.sleep(0.6)                      # poi più del tempo massimo per finire
            return super().riassumi(lavoro, controlla)
    comp = Compressore(cfg, [Lungo(0.0), RiassuntoreTagli()], None, log=lambda s: None)
    lav = comp.prepara(b)
    comp._esegui(lav)
    verifica("contrario: partito in tempo, si aspetta la fine anche oltre",
             lav.usato == "agente", str(lav.prove))
    cfg.contesto_riassunto_attesa_s = 0
    comp = Compressore(cfg, [AgenteFinto(attesa=0.5), RiassuntoreTagli()], None,
                       log=lambda s: None)
    lav = comp.prepara(b)
    comp._esegui(lav)
    verifica("contesto_riassunto_attesa_s 0: senza limite", lav.usato == "agente")
    verifica("predefinito 10 s", Config().contesto_riassunto_attesa_s == 10.0)

    # Q11 (06/10): un tetto in tutto, anche dopo il primo pezzo e se cede e riparte
    print("── riassunto dell'agente con un tetto in tutto (Q11) ──")
    cfg.contesto_riassunto_attesa_s = 0.3
    cfg.contesto_riassunto_max_s = 0.5

    class Infinito(AgenteFinto):
        def riassumi(self, lavoro, controlla=None):
            controlla()                          # parte subito…
            for _ in range(400):                 # …e non finisce (4 s)
                time.sleep(0.01)
                controlla()
            return super().riassumi(lavoro, controlla)
    inf = Infinito(0.0)
    comp = Compressore(cfg, [inf, RiassuntoreTagli()], None, log=lambda s: None)
    lav = comp.prepara(b)
    t0 = time.monotonic()
    comp._esegui(lav)
    s = time.monotonic() - t0
    verifica("partito ma senza fine: dopo il tetto i tagli, e il suo stream si chiude",
             lav.usato == "tagli" and s < 1.2 and lav.prove[0].startswith("agente: TroppoLungo")
             and inf.cliente.interrotti, f"{lav.usato} {s:.2f} s {lav.prove}")
    from calliope.compressione import Interrotto as Ceduto

    class Cedevole(AgenteFinto):
        def __init__(self):
            super().__init__(0.0)
            self.tentativi = 0

        def riassumi(self, lavoro, controlla=None):
            self.tentativi += 1
            controlla()
            time.sleep(0.2)
            raise Ceduto()                       # cede alla voce e riparte da capo
    ced = Cedevole()
    comp = Compressore(cfg, [ced, RiassuntoreTagli()], None, log=lambda s: None)
    lav = comp.prepara(b)
    t0 = time.monotonic()
    comp._esegui(lav)
    s = time.monotonic() - t0
    verifica("ceduto e ripartito: il tetto conta dal primo tentativo",
             lav.usato == "tagli" and ced.tentativi < 6 and s < 1.2
             and any(p.startswith("agente: TroppoLungo") for p in lav.prove),
             f"{ced.tentativi} tentativi, {s:.2f} s, {lav.prove}")
    cfg.contesto_riassunto_max_s = 5.0
    comp = Compressore(cfg, [Lungo(0.0), RiassuntoreTagli()], None, log=lambda s: None)
    lav = comp.prepara(b)
    comp._esegui(lav)
    verifica("contrario: finito entro il tetto, il riassunto dell'agente",
             lav.usato == "agente", str(lav.prove))
    verifica("predefinito del tetto 60 s", Config().contesto_riassunto_max_s == 60.0)


# ─────────────────── prima voce sentita (e2e del 06/10) ───────────────────
def prova_prima_voce():
    """Il satellite dice quando comincia a suonare ogni frase (`suona`); il server lo segna,
    il turno ha `prima_voce_s`, latenza e cruscotto la mostrano. Un satellite vecchio non lo
    dice: niente campo, niente errori."""
    print("── prima voce sentita (satellite) ──")
    import numpy as np
    from calliope.satellite import server as SV
    from calliope.satellite.client import Riproduttore
    from calliope.ciclo import Ciclo

    class Flusso:
        def __init__(self, samplerate, channels, dtype, device):
            self.samplerate, self.latency = samplerate, 0.05

        def start(self):
            pass

        def stop(self):
            pass

        def close(self):
            pass

        def write(self, data):
            time.sleep(len(data) / 2 / self.samplerate)

    cfg = Config()
    cfg.tts_keepalive = False
    suonate = []
    rp = Riproduttore(cfg, Flusso, None, rate=16000,
                      suonata=lambda i, u: suonate.append((i, u, time.monotonic())))
    pcm = (np.ones(16000 // 2, dtype="<i2") * 1000).tobytes()       # 0,5 s
    t0 = time.monotonic()
    rp.frase(1, 7, "Ciao.", 16000, len(pcm))
    rp.pezzo(7, pcm)
    rp.frase(1, 8, "Come stai?", 16000, len(pcm))
    rp.pezzo(8, pcm)
    fine = time.monotonic() + 3
    while len(suonate) < 2 and time.monotonic() < fine:
        time.sleep(0.02)
    verifica("satellite: una «suona» per frase, al primo blocco, con il ritardo dell'uscita",
             [x[:2] for x in suonate] == [(7, 0.05), (8, 0.05)]
             and suonate[0][2] - t0 < 0.3 and suonate[1][2] - t0 >= 0.4, str(suonate))
    # Server: il messaggio, il collegamento, l'uscita remota e Speaker
    coll = SV.Collegamento(None, {"id": 1, "nome": "studio"}, "h")
    srv = SimpleNamespace(attivo_pronto=lambda sat_id=None: coll)
    coll.invia = lambda **k: True
    coll.invia_bin = lambda b: True
    u = SV.UscitaRemota(srv)
    u.invia(3, "Un attimo.", pcm, 16000)
    u.invia(3, "Sono le dieci.", pcm, 16000)
    verifica("uscita remota: senza «suona» (satellite vecchio) nessuna prima voce",
             u.prima_voce(3) is None)
    t_srv = time.monotonic()
    SV.ServerSatelliti._messaggio(SimpleNamespace(), coll, {"nome": "studio"}, "suona",
                                  {"tipo": "suona", "id": 1, "uscita_s": 0.08})
    SV.ServerSatelliti._messaggio(SimpleNamespace(), coll, {"nome": "studio"}, "suona",
                                  {"tipo": "suona", "id": 2, "uscita_s": 0.08})
    pv = u.prima_voce(3)
    verifica("server: la prima frase del turno (anche quella d'attesa), più il ritardo "
             "dell'uscita", pv is not None and 0.07 <= pv - t_srv <= 0.2, str(pv))
    SV.ServerSatelliti._messaggio(SimpleNamespace(), coll, {"nome": "studio"}, "suona",
                                  {"tipo": "suona", "id": "x", "uscita_s": "nan"})
    verifica("server: un «suona» rotto si scarta", "x" not in coll.suonate)
    sp = SimpleNamespace(remota=u, turno=3)
    from calliope.tts import Speaker
    verifica("Speaker.prima_voce con il satellite", Speaker.prima_voce(sp) == pv)
    # Il turno nel registro: da t0 come prima_frase_s
    rec = {"prima_frase_s": 0.6, "fine_parlato_s": 1.3}
    finto = SimpleNamespace(speaker=SimpleNamespace(prima_voce=lambda: t_srv + 0.9), rec=rec)
    Ciclo._prima_voce(finto, SimpleNamespace(t0_mono=t_srv))
    verifica("ciclo: prima_voce_s nel turno", 0.85 <= rec.get("prima_voce_s", 0) <= 0.95, str(rec))
    finto.speaker.prima_voce = lambda: None
    rec2 = {"prima_frase_s": 0.6}
    finto.rec = rec2
    Ciclo._prima_voce(finto, SimpleNamespace(t0_mono=t_srv))
    verifica("contrario: senza la misura nessun campo", "prima_voce_s" not in rec2)
    # Latenza e cruscotto
    turni = [turno("2026-10-06", 1.0, fine_parlato_s=1.7, prima_voce_s=1.4) for _ in range(5)]
    turni += [turno("2026-10-06", 1.2) for _ in range(5)]
    d = latenza.per_giorno(turni)["2026-10-06"]
    verifica("latenza: prima voce sentita e dalla fine del parlato",
             d["prima_voce"]["n"] == 5 and d["prima_voce"]["mediana"] == 1.4
             and abs(d["prima_voce"]["sentita"] - 2.1) < 1e-9, str(d["prima_voce"]))
    t = latenza.testo({"2026-10-06": d})
    verifica("latenza: la riga nel terminale",
             "prima voce sentita 1,40 s" in t and "dalla fine del parlato 2,10 s" in t, t)
    from calliope.schermi import cruscotto as CR
    js = (Path(CR.__file__).parent / "pagina" / "schermo.js").read_text(encoding="utf-8")
    verifica("cruscotto: la prima voce sentita nei dati e nella pagina",
             '"prima_voce": d.get("prima_voce")' in Path(CR.__file__).read_text("utf-8")
             and "prima voce sentita" in js)


# ─────────────────── la prima frase a pezzi (07/10) ───────────────────
def prova_voce_a_pezzi():
    """Dal testo alla voce (07/10, DGX: ~0,9 s tra prima frase pronta e voce sentita sullo
    studio, quasi tutto sintesi di Piper della prima frase intera): la prima frase lunga del
    turno in due pezzi dopo una virgola, i due punti o il punto e virgola; la misura della
    sintesi nel registro e nella latenza; il telefono che dice quando suona."""
    print("── prima frase a pezzi ──")
    from calliope import tts
    from calliope.ciclo import Ciclo
    pp = tts.primo_pezzo
    # Velocità della voce e costo della sintesi (07/10): serena-high sulla DGX con 8 thread
    # (~19 caratteri al secondo, 3,5 ms a carattere) e il portatile carico (17, 18,7 ms)
    DGX = dict(parlato_car_s=19.0, sintesi_s_car=0.0035)
    LENTO = dict(parlato_car_s=17.0, sintesi_s_car=0.0187)
    f = ("Sono qui, pronta a tutto, anche se non sono sicura di aver capito cosa ti abbiano "
         "detto esattamente.")
    verifica("frase lunga: «Sono qui,» sotto il minimo, si taglia alla virgola dopo",
             pp(f, 60, **DGX) == ("Sono qui, pronta a tutto,", "anche se non sono sicura di "
                                  "aver capito cosa ti abbiano detto esattamente."),
             str(pp(f, 60, **DGX)))
    dormire = ("Per dormire meglio, potresti provare a mantenere orari regolari, limitare "
               "l'uso di schermi prima di coricarti e creare un ambiente fresco e buio.")
    verifica("caso vero del 07/10: «Per dormire meglio,» ora basta (prima ~65 caratteri)",
             (pp(dormire, 60, **DGX) or ("",))[0] == "Per dormire meglio,",
             str(pp(dormire, 60, **DGX)))
    verifica("caso vero: «Visto che hai lo smoker,» (prima ~95 caratteri)",
             (pp("Visto che hai lo smoker, potresti tentare una frittata al forno con zucchine "
                 "e un tocco di formaggio, oppure una torta salata veloce.", 60, **DGX)
              or ("",))[0] == "Visto che hai lo smoker,")
    verifica("macchina lenta: lo stesso taglio non copre il resto, si va alla pausa dopo",
             (pp(dormire, 60, **LENTO) or ("",))[0]
             == "Per dormire meglio, potresti provare a mantenere orari regolari,",
             str(pp(dormire, 60, **LENTO)))
    g = ("Allora abbiamo un atleta completo: tra colpi di gomito e maestria orientale, "
         "spero che il tuo corpo sia pronto.")
    verifica("i due punti valgono come la virgola",
             (pp(g, 60, **DGX) or ("",))[0] == "Allora abbiamo un atleta completo:",
             str(pp(g, 60, **DGX)))
    verifica("punto e virgola", (pp("Ho acceso la luce in cucina; quella del salotto era già "
                                    "accesa da un pezzo, la lascio così.", 60, **DGX)
                                 or ("",))[0] == "Ho acceso la luce in cucina;")
    paradosso = ("Hai ragione, è un paradosso degno di un romanzo di fantascienza: cerchiamo di "
                 "fare progresso e finiamo per girare in tondo come un disco graffiato.")
    verifica("contrario: primo pezzo sotto il minimo («Hai ragione,», 12 caratteri)",
             (pp(paradosso, 60, **DGX) or ("",))[0].endswith("fantascienza:"),
             str(pp(paradosso, 60, **DGX)))
    verifica("con il minimo più basso (e una voce che lo permette) si taglia lì",
             (pp(paradosso, 60, 10, 19.0, 0.002) or ("",))[0] == "Hai ragione,",
             str(pp(paradosso, 60, 10, 19.0, 0.002)))
    verifica("contrario: «Beh,» da solo mai, anche con la voce più veloce",
             (pp("Beh, il Calisthenics non è una passeggiata, specialmente quando devi "
                 "sollevare tutto te stesso.", 60, **DGX) or ("",))[0]
             == "Beh, il Calisthenics non è una passeggiata,")
    verifica("contrario: frase corta non si tocca", pp("Non ho lavori in corso.", 60) is None)
    verifica("contrario: spento con 0", pp(f, 0, **DGX) is None)
    verifica("contrario: senza virgole resta intera (caso vero del motore elettrico)",
             pp("Un motore elettrico trasforma l'energia elettrica in energia meccanica "
                "sfruttando l'interazione tra campi magnetici.", 60, **DGX) is None)
    verifica("contrario: senza pause non si taglia a metà",
             pp("Domani mattina alle nove hai la riunione con il commercialista per il "
                "bilancio dell'anno scorso.", 60, **DGX) is None)
    verifica("contrario: la virgola dei decimali non è una pausa",
             pp("La temperatura in salotto adesso è di 21,5 gradi e l'umidità è al "
                "quarantotto per cento circa.", 60, **DGX) is None)
    verifica("contrario: il resto troppo corto non vale il taglio",
             pp("Ho controllato tutte le luci della casa e i sensori del giardino, va bene.",
                60, **DGX) is None)
    verifica("contrario: con una sintesi lentissima nessuna pausa basta, frase intera",
             pp(dormire, 60, parlato_car_s=15.0, sintesi_s_car=0.2) is None)

    # La stima della voce (calliope/taratura_voce.py): predefiniti, avvio, uso
    from calliope import taratura_voce as tv
    T = tv.Taratura(None)
    st0 = T.stima("voices/it_IT-serena-high.onnx", 8)
    verifica("taratura: senza misure i predefiniti prudenti",
             st0["fonte"] == "predefiniti" and st0["sintesi_s_car"] == tv.PREDEFINITI[
                 "sintesi_s_car"], str(st0))
    T.segna_avvio("voices/it_IT-serena-high.onnx", 8, 18.0, 0.004, {"2": 0.01, "8": 0.004})
    st1 = T.stima("voices/it_IT-serena-high.onnx", 8)
    verifica("taratura: dopo l'avvio vale la sua misura",
             st1["fonte"] == "avvio" and st1["sintesi_s_car"] == 0.004, str(st1))
    verifica("taratura: i thread scelti, anche per un'altra voce della stessa macchina",
             T.thread_scelto("voices/it_IT-serena-high.onnx") == 8
             and T.thread_scelto("voices/it_IT-paola-medium.onnx") == 8)
    verifica("taratura: con altri thread la misura non vale (si riparte dai predefiniti)",
             T.stima("voices/it_IT-serena-high.onnx", 4)["fonte"] == "predefiniti")

    def usa(t, voce, costo, parlato, n, car=80, thread=8):
        for _ in range(n):
            t.osserva(voce, thread, car, costo * car, car / parlato)
    usa(T, "voices/it_IT-serena-high.onnx", 0.002, 20.0, tv.MIN_USO - 1)
    verifica("taratura: con meno di MIN_USO sintesi vale ancora l'avvio",
             T.stima("voices/it_IT-serena-high.onnx", 8)["fonte"] == "avvio")
    T.osserva("voices/it_IT-serena-high.onnx", 8, 80, 2.0, 4.0)       # CPU presa da altro
    T.osserva("voices/it_IT-serena-high.onnx", 8, 5, 0.5, 0.3)        # troppo corta
    usa(T, "voices/it_IT-serena-high.onnx", 0.002, 20.0, 1)
    st2 = T.stima("voices/it_IT-serena-high.onnx", 8)
    verifica("taratura: dall'uso la mediana, anomali e frasi corte scartati",
             st2["fonte"] == "uso" and st2["n"] == tv.MIN_USO
             and abs(st2["sintesi_s_car"] - 0.002) < 1e-9
             and abs(st2["parlato_car_s"] - 20.0) < 1e-6, str(st2))
    usa(T, "voices/it_IT-paola-medium.onnx", 0.03, 15.0, tv.MIN_USO)
    lenta = T.stima("voices/it_IT-paola-medium.onnx", 8)
    verifica("taratura: separata per voce",
             abs(lenta["sintesi_s_car"] - 0.03) < 1e-9
             and abs(T.stima("voices/it_IT-serena-high.onnx", 8)["sintesi_s_car"] - 0.002)
             < 1e-9)
    veloce = T.stima("voices/it_IT-serena-high.onnx", 8)
    tv_v = pp(dormire, 60, 15, veloce["parlato_car_s"], veloce["sintesi_s_car"])
    tv_l = pp(dormire, 60, 15, lenta["parlato_car_s"], lenta["sintesi_s_car"])
    verifica("taratura: la stima cambia il taglio (voce veloce prima, lenta più avanti)",
             tv_v and tv_l and len(tv_v[0]) < len(tv_l[0]), f"{tv_v} / {tv_l}")
    with tempfile.TemporaryDirectory() as d:
        pf = Path(d) / tv.FILE
        T2 = tv.Taratura(pf)
        T2.segna_avvio("voices/it_IT-serena-high.onnx", 4, 18.0, 0.005, {"4": 0.005})
        usa(T2, "voices/it_IT-serena-high.onnx", 0.003, 19.0, tv.MIN_USO, thread=4)
        T2.salva()
        T3 = tv.Taratura(pf)
        st3 = T3.stima("voices/it_IT-serena-high.onnx", 4)
        verifica("taratura: salvata e riletta (sopravvive al riavvio)",
                 st3["fonte"] == "uso" and abs(st3["sintesi_s_car"] - 0.003) < 1e-9
                 and T3.thread_scelto("voices/it_IT-serena-high.onnx") == 4, str(st3))
        pf.write_text("{rotto", encoding="utf-8")
        verifica("contrario: file rovinato, si riparte dai predefiniti senza fermarsi",
                 tv.Taratura(pf).stima("voices/it_IT-serena-high.onnx", 4)["fonte"]
                 == "predefiniti")
        cfg_t = Config()
        cfg_t.config_dir = d
        cfg_t.tts_thread = 6
        verifica("thread: il numero scritto in tts_thread vince",
                 tv.thread_in_uso(cfg_t, "voices/it_IT-serena-high.onnx") == 6)
        cfg_t.tts_thread = "auto"
        tv.per(cfg_t).segna_avvio("voices/it_IT-serena-high.onnx", 4, 18.0, 0.005,
                                  {"4": 0.005})
        verifica("thread: «auto» usa la scelta della taratura",
                 tv.thread_in_uso(cfg_t, "voices/it_IT-serena-high.onnx") == 4)
        verifica("stato: la stima in una riga",
                 "4 thread, scelti dalla taratura" in (tv.testo_stato(cfg_t) or ""),
                 str(tv.testo_stato(cfg_t)))
    verifica("thread: «auto» senza taratura 8 (mai più dei processori)",
             tv.thread_in_uso(Config(), "voices/x.onnx") == min(8, os.cpu_count() or 8))
    from calliope.config import _tts_thread_valido
    ok_val = (_tts_thread_valido("auto") == "auto" and _tts_thread_valido(4) == 4
              and _tts_thread_valido("8") == 8)
    try:
        _tts_thread_valido("molti")
        ok_val = False
    except ValueError:
        pass
    verifica("config: tts_thread un numero o «auto»", ok_val)

    # Speaker con un'uscita remota finta e una sintesi finta (niente Piper)
    class Remota:
        def __init__(self):
            self.frasi, self._in_coda_s = [], 0.0

        def invia(self, turno, testo, audio, rate):
            self.frasi.append((turno, testo))

        def fine_turno(self):
            return [x[1] for x in self.frasi]

        def ferma(self, turno):
            pass

        def prima_voce(self, turno):
            return None

    cfg = Config()
    voce = SimpleNamespace(config=SimpleNamespace(sample_rate=16000))
    base = SimpleNamespace(_voices={}, voice=voce, pronuncia=None,
                           _voices_lock=threading.Lock(), _fillers={})
    rem = Remota()
    sp = tts.Speaker(cfg, uscita=rem, base=base)
    sp._pcm = lambda v, testo: b"\0\0" * 16 * len(testo)
    sp._taratura = tv.Taratura(None)
    t0 = time.monotonic()
    sp.start_turn()
    sp.say(f)
    sp.say("E poi una frase lunga anche lei, con una virgola che però non si taglia più.")
    sp.wait()
    testi = [x[1] for x in rem.frasi]
    verifica("Speaker: la prima frase del turno in due pezzi, la seconda intera",
             testi == ["Sono qui, pronta a tutto,", f[len("Sono qui, pronta a tutto, "):],
                       "E poi una frase lunga anche lei, con una virgola che però non si "
                       "taglia più."], str(testi))
    verifica("Speaker: in played i pezzi, che uniti danno la frase",
             " ".join(sp.played[:2]) == f, str(sp.played))
    vp = sp.voce_pronta()
    verifica("Speaker: il primo audio del turno pronto, con il tempo di sintesi",
             vp is not None and vp[0] >= t0 and 0 <= vp[1] < 1, str(vp))
    rem.frasi.clear()
    sp.start_turn()
    sp.say(f)
    sp.wait()
    verifica("Speaker: al turno dopo si taglia di nuovo", len(rem.frasi) == 2)

    # Un Piper finto lento: la stima dall'uso converge al suo costo e il taglio si sposta
    sp2 = tts.Speaker(cfg, uscita=Remota(), base=base)
    sp2._taratura = tv.Taratura(None)

    def pcm_lento(v, testo):
        time.sleep(0.001 * len(testo))           # 1 ms a carattere
        return b"\0\0" * int(16000 * len(testo) / 15)   # 15 caratteri al secondo
    sp2._pcm = pcm_lento
    sp2.start_turn()
    for _ in range(tv.MIN_USO + 2):
        sp2.say("Una frase di prova abbastanza lunga da contare.")
    sp2.wait()
    st_l = sp2.stima_voce()
    verifica("Piper finto lento: la stima converge (1 ms a carattere, 15 al secondo)",
             st_l["fonte"] == "uso" and 0.0009 <= st_l["sintesi_s_car"] < 0.004
             and abs(st_l["parlato_car_s"] - 15) < 0.5, str(st_l))
    sp.start_turn()
    verifica("Speaker: un turno nuovo non ha ancora il primo audio", sp.voce_pronta() is None)
    cfg.tts_spezza_prima = 0
    rem.frasi.clear()
    sp.start_turn()
    sp.say(f)
    sp.wait()
    verifica("contrario: tts_spezza_prima 0, la frase intera", [x[1] for x in rem.frasi] == [f])
    verifica("predefiniti: 60 caratteri, primo pezzo da 15, thread «auto»",
             Config().tts_spezza_prima == 60 and Config().tts_thread == "auto"
             and Config().tts_primo_pezzo_min == 15)
    from calliope.config import _bool_env
    os.environ["PROVA_TARATURA_X"] = "0"
    verifica("taratura accesa se l'ambiente non dice altro (le prove la spengono: "
             "CALLIOPE_TTS_TARATURA=0 nel runner)",
             _bool_env("PROVA_TARATURA_NON_C_E", True) is True
             and _bool_env("PROVA_TARATURA_X", True) is False)
    os.environ.pop("PROVA_TARATURA_X", None)

    # Il registro: voce_pronta_s e sintesi_s da t0, come prima_voce_s
    rec = {"prima_frase_s": 1.0}
    finto = SimpleNamespace(rec=rec, speaker=SimpleNamespace(
        prima_voce=lambda: 100.0 + 1.5, voce_pronta=lambda: (100.0 + 1.3, 0.25)))
    Ciclo._prima_voce(finto, SimpleNamespace(t0_mono=100.0))
    verifica("ciclo: voce_pronta_s e sintesi_s nel turno",
             rec.get("voce_pronta_s") == 1.3 and rec.get("sintesi_s") == 0.25
             and rec.get("prima_voce_s") == 1.5, str(rec))
    rec2 = {"prima_frase_s": 1.0}
    finto.rec = rec2
    finto.speaker = SimpleNamespace(prima_voce=lambda: None)      # Speaker vecchio o finto
    Ciclo._prima_voce(finto, SimpleNamespace(t0_mono=100.0))
    verifica("contrario: senza la misura nessun campo", rec2 == {"prima_frase_s": 1.0}, str(rec2))

    # La latenza: dal testo alla voce, scomposto
    turni = [turno("2026-10-07", 1.0, prima_voce_s=1.9, voce_pronta_s=1.6) for _ in range(4)]
    turni += [turno("2026-10-07", 3.0, prima_voce_s=1.2)]       # frase d'attesa: esclusa
    giorni = latenza.per_giorno(turni)
    d = giorni["2026-10-07"]["prima_voce"]
    verifica("latenza: distacco, sintesi e consegna (senza i turni con la frase d'attesa)",
             abs(d["distacco"] - 0.9) < 1e-9 and abs(d["sintesi"] - 0.6) < 1e-9
             and abs(d["consegna"] - 0.3) < 1e-9 and d["n_scomposti"] == 4, str(d))
    t = latenza.testo(giorni)
    verifica("latenza: la riga nel terminale",
             "dal testo alla voce 0,90 s" in t and "sintesi 0,60 s, rete e uscita 0,30 s" in t, t)

    # Il telefono dice quando la voce comincia (prima `prima_voce_s` mancava sempre)
    pag = Path(tts.__file__).parent / "schermi" / "pagina" / "telefono"
    vj = (pag / "voce.js").read_text(encoding="utf-8")
    tj = (pag / "telefono.js").read_text(encoding="utf-8")
    verifica("telefono: «suona» al primo pezzo con il ritardo dell'uscita del browser",
             "this.onSuona(f.id, uscita)" in vj and "outputLatency" in vj
             and 'tipo: "suona"' in tj and "player.onSuona" in tj)


def prova_voce_gpu():
    """Piper sulla CPU o sulla GPU secondo la macchina (07/10, `tts_dispositivo`): macchine
    finte (portatile da 8 GB, DGX con memoria unificata), una sintesi finta più o meno veloce,
    la scelta e il motivo salvati, il ripiego sulla CPU. Niente CUDA vera."""
    from calliope import taratura_voce as tv
    from calliope import tts
    from calliope.config import _tts_dispositivo_valido
    PORTATILE = {"unificata": False, "totale_gb": 7.96, "libera_gb": 0.5}
    PORTATILE_VUOTO = {"unificata": False, "totale_gb": 7.96, "libera_gb": 6.0}
    DGX = {"unificata": True, "totale_gb": 119.7, "libera_gb": 21.0}
    DGX_PIENA = {"unificata": True, "totale_gb": 119.7, "libera_gb": 6.0}
    GRANDE = {"unificata": False, "totale_gb": 32.0, "libera_gb": 10.0}
    verifica("posto: portatile da 8 GB con voce e Whisper caricati, niente GPU",
             not tv.posto_gpu(PORTATILE)[0], tv.posto_gpu(PORTATILE)[1])
    verifica("posto: portatile da 8 GB anche con la VRAM libera (la tengono voce e Whisper)",
             not tv.posto_gpu(PORTATILE_VUOTO)[0]
             and "voce e Whisper" in tv.posto_gpu(PORTATILE_VUOTO)[1])
    verifica("posto: memoria unificata grande sì", tv.posto_gpu(DGX)[0], tv.posto_gpu(DGX)[1])
    verifica("contrario: memoria unificata senza margine, no", not tv.posto_gpu(DGX_PIENA)[0])
    verifica("posto: GPU dedicata da 32 GB con 10 liberi sì", tv.posto_gpu(GRANDE)[0])
    verifica("contrario: senza nvidia-smi nessuna GPU", not tv.posto_gpu(None)[0])

    # Sintesi finta: la «sessione» dice quanto costa la frase fissa
    class Voce:
        def __init__(self):
            self.session = "cpu"
            self.config = SimpleNamespace(sample_rate=16000)
    costi = {"cpu": 0.02, "cuda": 0.005}

    def sintetizza(voice, testo):
        time.sleep(costi[voice.session])
        return b"\0\0" * 16000
    aperte = []

    def sessione_fn(path):
        aperte.append(path)
        return "cuda"
    cpu = tv.misura(sintetizza, Voce(), 16000)[0]
    s, sess, info = tv.prova_dispositivo(Voce(), "v.onnx", sintetizza, 16000, cpu,
                                         mem_fn=lambda: PORTATILE, sessione_fn=sessione_fn)
    verifica("portatile da 8 GB: CPU, senza nemmeno aprire la GPU",
             s == "cpu" and sess is None and not aperte and info["causa"] == "memoria", str(info))
    s, sess, info = tv.prova_dispositivo(Voce(), "v.onnx", sintetizza, 16000, cpu,
                                         mem_fn=lambda: DGX, sessione_fn=sessione_fn)
    verifica("memoria unificata grande e GPU misurata 4 volte più veloce: GPU",
             s == "cuda" and sess == "cuda" and info["causa"] == "misura"
             and info["cuda_s_car"] < info["cpu_s_car"] and "memoria unificata" in info["motivo"],
             str(info))
    costi["cuda"] = 0.015
    s, sess, info = tv.prova_dispositivo(Voce(), "v.onnx", sintetizza, 16000, cpu,
                                         mem_fn=lambda: DGX, sessione_fn=sessione_fn)
    verifica("contrario: GPU solo un po' più veloce (sotto carico non lo sarebbe), CPU",
             s == "cpu" and sess is None and "non abbastanza" in info["motivo"], str(info))

    def rotta(path):
        raise OSError("libcudnn.so: cannot open shared object file")
    s, sess, info = tv.prova_dispositivo(Voce(), "v.onnx", sintetizza, 16000, cpu,
                                         mem_fn=lambda: DGX, sessione_fn=rotta)
    verifica("contrario: librerie di CUDA mancanti, CPU con il motivo",
             s == "cpu" and info["causa"] == "errore" and "libcudnn" in info["motivo"])

    # La scelta salvata, ricontrollata all'apertura, e `calliope stato`
    vero_cuda = tv.cuda_disponibile
    try:
        with tempfile.TemporaryDirectory() as d:
            cfg = Config()
            cfg.config_dir = d
            voce = "voices/it_IT-serena-high.onnx"
            tv.cuda_disponibile = lambda: False
            verifica("onnxruntime senza CUDA: CPU (il portatile, Windows)",
                     tv.dispositivo_in_uso(cfg, voce) == ("cpu", "onnxruntime senza CUDA")
                     and not tv.da_provare(cfg, voce))
            tv.cuda_disponibile = lambda: True
            verifica("auto prima della taratura: CPU, GPU da provare",
                     tv.dispositivo_in_uso(cfg, voce)[0] == "cpu" and tv.da_provare(cfg, voce))
            T = tv.per(cfg)
            T.segna_dispositivo(voce, {"scelta": "cpu", "causa": "memoria",
                                       "motivo": "memoria unificata con 6,0 GB liberi"})
            verifica("CPU per mancanza di posto: si riprova al prossimo avvio",
                     tv.da_provare(cfg, voce))
            T.segna_dispositivo(voce, {"scelta": "cuda", "causa": "misura",
                                       "motivo": "memoria unificata con 21,0 GB liberi",
                                       "cpu_s_car": 0.004, "cuda_s_car": 0.0007})
            T.segna_avvio(voce, "cuda", 18.0, 0.0007)
            verifica("GPU scelta dalla taratura: si apre sulla GPU, non si riprova",
                     tv.dispositivo_in_uso(cfg, voce, mem_fn=lambda: DGX)[0] == "cuda"
                     and not tv.da_provare(cfg, voce)
                     and tv.Taratura(Path(d) / tv.FILE).dispositivo_scelto(voce)["scelta"]
                     == "cuda")
            ora = tv.dispositivo_in_uso(cfg, voce, mem_fn=lambda: DGX_PIENA)
            verifica("contrario: GPU scelta ma ora la memoria non basta, CPU",
                     ora[0] == "cpu" and "ora" in ora[1], str(ora))
            st = tv.testo_stato(cfg) or ""
            verifica("stato: sulla GPU con il motivo e la misura della GPU",
                     "sulla GPU" in st and "GPU: memoria unificata" in st and "0,7 ms" in st, st)
            verifica("stato: la chiave delle misure è «cuda»",
                     tv.sessione_in_uso(cfg, voce) == "cuda")
            for _ in range(tv.MIN_USO):
                T.osserva(voce, "cuda", 80, 0.005 * 80, 80 / 18.0)
            ora = tv.dispositivo_in_uso(cfg, voce, mem_fn=lambda: DGX)
            verifica("dall'uso la GPU è più lenta della CPU misurata: si torna alla CPU",
                     ora == ("cpu", "dall'uso la GPU non è più veloce della CPU"), str(ora))
            cfg.tts_dispositivo = "cpu"
            verifica("tts_dispositivo: cpu scritto vince",
                     tv.dispositivo_in_uso(cfg, voce, mem_fn=lambda: DGX)
                     == ("cpu", "scritto in tts_dispositivo") and not tv.da_provare(cfg, voce))
            cfg.tts_dispositivo = "cuda"
            verifica("tts_dispositivo: cuda scritto vince (anche senza posto)",
                     tv.dispositivo_in_uso(cfg, voce, mem_fn=lambda: PORTATILE)[0] == "cuda")
            tv.cuda_disponibile = lambda: False
            verifica("contrario: cuda scritto ma onnxruntime senza CUDA, CPU con il motivo",
                     "non ha CUDA" in tv.dispositivo_in_uso(cfg, voce)[1])
            tv.cuda_disponibile = lambda: True

            # Ripiego all'apertura: la sessione CUDA si apre, la prima sintesi fallisce
            class VocePiper:
                def __init__(self):
                    self.session = "cpu"

                def phonemize(self, t):
                    return [t]

                def synthesize(self, testo):
                    if self.session == "cuda":
                        raise RuntimeError("cuDNN is unavailable")
                    yield b""
            vero_sess = tv.sessione_cuda
            tv.sessione_cuda = lambda p: "cuda"
            try:
                v = VocePiper()
                buf = io.StringIO()
                with redirect_stdout(buf):
                    su = tts._su_gpu(cfg, v, voce)
                verifica("ripiego: GPU che fallisce alla prima frase, la voce resta sulla CPU",
                         su is False and v.session == "cpu"
                         and getattr(v, "calliope_dispositivo", None) is None
                         and "resta sulla CPU" in buf.getvalue(), buf.getvalue())
                VocePiper.synthesize = lambda self, testo: iter([b""])
                v = VocePiper()
                with redirect_stdout(io.StringIO()):
                    su = tts._su_gpu(cfg, v, voce)
                verifica("GPU che funziona: sessione CUDA e chiave «cuda»",
                         su is True and v.session == "cuda" and tv.thread_di(v) == "cuda")
            finally:
                tv.sessione_cuda = vero_sess
    finally:
        tv.cuda_disponibile = vero_cuda
    ok_val = all(_tts_dispositivo_valido(x) == x for x in ("auto", "cpu", "cuda"))
    try:
        _tts_dispositivo_valido("gpu")
        ok_val = False
    except ValueError:
        pass
    verifica("config: tts_dispositivo auto, cpu o cuda", ok_val)


prova_guardiano()
prova_ripresa()
prova_ripresa_con_tool()
prova_registro()
prova_prima_voce()
prova_voce_a_pezzi()
prova_voce_gpu()
prova_compressione()
print(f"\n{'Tutto ok' if not errori else f'{errori} errori'}")
sys.exit(1 if errori else 0)
