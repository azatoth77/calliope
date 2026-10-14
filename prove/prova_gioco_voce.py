"""I comandi a voce di un gioco a secco (11/10/2026, richiesta approvata da Dario: «un gioco può
usare la voce come modalità di interazione»; calliope/gioco_voce.py, calliope/schermi/giochi.py,
calliope/ciclo.py, docs/aree/giochi.md).

- **manifesto**: i comandi a voce dalla macchina a stati (dal 14/10 l'unico formato: niente più
  `scheda.ascolta` piatto), validati (forme riservate, doppioni, il nome di chi gioca solo senza
  rete), le parole per chi approva;
- **server** (Giochi con l'hub vero, senza browser): il riquadro sceglie un sottoinsieme dei
  comandi dichiarati, mai comandi nuovi; la mossa porta solo il nome del comando e, se il
  manifesto lo chiede, quello di chi gioca; chiuso, guasto o senza segni dalla pagina non
  ascolta; anche la partita di prova riceve i comandi (sono un ingresso, non un ponte); gli
  schermi di un satellite;
- **ciclo** (calliope/ciclo.py con ascolto, Whisper, voce e Brain finti, il gioco «porte» su uno
  schermo vero): la regola `gioco_comando` e i suoi contrari (parole dentro una frase più lunga,
  nessun gioco aperto, gioco sullo schermo di un altro satellite, comando non attivo, una
  domanda di Calliope in sospeso); la finestra senza nome (l'ascolto si allunga, il pallino
  «ascolto», solo le forme dell'elenco, il resto ignorato e non conservato, il tetto di tempo);
  il contesto e `gioco_comando` per il modello; il nome di chi gioca solo con la voce
  riconosciuta; la latenza della mossa;
- **prova di fumo** dei giochi con i comandi a caso tra gli attivi (Node, se c'è).

Il gioco delle prove è `prove/giochi/porte` (dal 14/10 con la macchina a stati: i comandi a voce
sono `porta_1` … `porta_3` e quelli di Calliope, `inizia`, `avanti`, `ancora`).

    python prove/prova_gioco_voce.py
"""
import concurrent.futures
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from prova_ciclo import Ascolto, Cervello, ChiParla, Persone, Voce, Whisper  # noqa: E402
from prova_giochi import Ambiente, FINTO, file_gioco  # noqa: E402

from calliope import corsie  # noqa: E402
from calliope.agenti.sandbox import Isolamento, Sandbox  # noqa: E402
from calliope.ciclo import Ciclo, Servizi  # noqa: E402
from calliope.cortesia import Cortesia  # noqa: E402
from calliope.estensioni import scheda as SC  # noqa: E402
from calliope.estensioni.manifesto import ManifestoNonValido, permessi_in_parole, valida  # noqa: E402
from calliope.schermi import giochi as GI  # noqa: E402
from calliope.tools.schermi import _gioco_comando, gioco_spec  # noqa: E402

errori = 0
T0 = time.perf_counter()
# I comandi a voce del gioco delle porte (macchina.ascolta: quelli di Calliope, poi le porte)
TUTTI = ["inizia", "avanti", "ancora", "anchio", "porta_1", "porta_2", "porta_3"]
# Il numero dell'istantanea per partita e schermo (14/10: il motore la manda dopo ogni mossa)
_N: dict = {}


def stato(a, S, pid, comandi, fase="turno", **altro):
    """L'istantanea del motore come la manda il riquadro (14/10, passo 2): i comandi a voce
    attivi vengono da qui. Il risultato della pagina."""
    k = (pid, S["id"])
    _N[k] = _N.get(k, 0) + 1
    # (la frequenza dei messaggi della pagina non è ciò che si prova qui)
    a.giochi.partite[pid].posti[S["id"]].messaggi.clear()
    prep = fase == "preparazione"
    ist = {"n": _N[k], "fase": fase, "tocca": None if prep else 0, "turno": 0 if prep else 1,
           "giocatori": [] if prep else [{"nome": "Giocatore 1", "punti": 0}], "esito": None,
           "comandi": list(comandi)}
    ist.update(altro)
    return a.pagina(S, {"partita": pid, "tipo": "stato", "istantanea": ist})


def senza_n(d):
    return {k: v for k, v in d.items() if k != "n"}


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


# ═══════════════════════════ manifesto ═══════════════════════════

def prova_manifesto():
    sezione("manifesto: i comandi a voce della macchina")
    m, _ = file_gioco("porte")
    mv = valida(m)
    a = mv["scheda"].get("ascolta") or {}
    verifica("il gioco «porte» è valido, puro, con i comandi delle fasi e il nome di chi gioca",
             SC.e_gioco_puro(mv) and list(a.get("comandi") or {}) == TUTTI
             and a.get("giocatore") is True, str(a))
    parole = permessi_in_parole(mv)
    verifica("chi approva sente che si gioca a voce, con il nome di chi gioca",
             "si gioca a voce o toccando" in parole and "il nome di chi gioca" in parole, parole)

    def errore(comandi=None, **altro):
        mm = json.loads(json.dumps(m))
        if comandi is not None:
            mm["scheda"]["macchina"]["fasi"]["turno"]["comandi"].update(comandi)
        mm["scheda"].update({k: v for k, v in altro.items() if k != "giocatore"})
        if "giocatore" in altro:
            mm["scheda"]["macchina"]["giocatore"] = altro["giocatore"]
        if altro.get("azioni"):
            mm["permessi"] = {"rete": {"host": ["api.esempio.it"]}}
        try:
            valida(mm)
            return None
        except ManifestoNonValido as e:
            return str(e)
    for nome, com, altro, attesa in [
            ("un'uscita come forma", {"via": ["esci"]}, {}, "esci"),
            ("«basta» come forma", {"via": ["basta"]}, {}, "basta"),
            ("forma troppo lunga", {"x": ["apri subito la porta numero uno"]}, {}, "parole"),
            ("la stessa forma di un'altra porta", {"uno": ["1"]}, {}, "vale sia per"),
            ("«ascolta» piatto (il formato di prima)", None,
             {"ascolta": {"comandi": {"uno": ["uno"]}}}, "non c'è più"),
            ("il nome di chi gioca con rete_leggi", None,
             {"giocatore": True, "azioni": ["rete_leggi"]}, "giocatore")]:
        e = errore(com, **altro)
        verifica(f"rifiutato: {nome}", e is not None and attesa in e, e or "")
    t = valida(file_gioco("tris")[0])["scheda"]["ascolta"]
    verifica("contrario: senza «giocatore» nella macchina la mossa non porta nomi",
             t["giocatore"] is False and "casella_9" in t["comandi"], str(t)[:200])


# ═══════════════════════════ server ═══════════════════════════

class Coll(types.SimpleNamespace):
    """Un satellite collegato (Collegamento): id, schermo e stanza."""


class Satelliti:
    def __init__(self, colls):
        self.colls = colls
        self.attivo = None

    def per_id(self, sid):
        return self.colls.get(sid)

    def per_schermo(self, sid):
        return next((c for c in self.colls.values() if c.schermo_id == sid), None)


def prova_server(tmp: Path):
    sezione("server: comandi attivi, mossa, chiusura, partita di prova")
    a = Ambiente(tmp)
    a.installa("porte")
    a.installa("tris")
    A, B = a.abbina("A", "studio"), a.abbina("B", "studio")
    C = a.abbina("C", "studio")
    sat = a.hub.satelliti = Satelliti({7: Coll(id=7, schermo_id=A["id"], stanza="studio"),
                                       8: Coll(id=8, schermo_id=B["id"], stanza="studio"),
                                       9: Coll(id=9, schermo_id=None, stanza="studio")})
    verifica("schermi della voce: il satellite con il suo schermo → solo quello",
             a.giochi.schermi_voce(sat.per_id(7)) == [A["id"]])
    verifica("…un satellite senza schermo → quelli della sua stanza che non sono di un altro "
             "satellite", a.giochi.schermi_voce(sat.per_id(9)) == [C["id"]],
             str(a.giochi.schermi_voce(sat.per_id(9))))
    ev = threading.Event()
    a.giochi.aggiungi_sveglia(ev)
    out = a.chiama("est_porte", {}, "Dario", schermo=A)
    pid = out.get("partita")
    verifica("prima di «pronto» nessun gioco ascolta", a.giochi.ascolto([A["id"]]) is None)
    r = a.pagina(A, {"partita": pid, "tipo": "pronto"})
    verifica("«pronto»: il riquadro è aperto ma senza istantanea non ascolta ancora (il server "
             "non deduce lo stato)", r.get("ok") and "comandi" not in r["avvio"]
             and a.giochi.ascolto([A["id"]]) is None, str(r.get("avvio")))
    r = stato(a, A, pid, ["inizia"], fase="preparazione")
    info = a.giochi.ascolto([A["id"]])
    verifica("la prima istantanea (preparazione): ascolta «inizia», e la sveglia della voce suona",
             r.get("ok") and info is not None and list(info["comandi"]) == ["inizia"]
             and ev.is_set() and info["giocatore"] is True and info["schermo"] == A["id"]
             and info["istantanea"]["fase"] == "preparazione", str(info))
    verifica("contrario: sullo schermo di un altro satellite niente",
             a.giochi.ascolto([B["id"]]) is None)
    ev.clear()
    r = stato(a, A, pid, ["porta_1", "porta_3"])
    verifica("il motore nel riquadro sceglie un sottoinsieme dei comandi della fase",
             r.get("ok") and list(a.giochi.ascolto([A["id"]])["comandi"])
             == ["porta_1", "porta_3"], str(r))
    for nome, attivi in (("un comando nuovo", ["porta_1", "porta_4"]), ("un numero", [1]),
                         ("non un elenco", "porta_1"), ("troppi", ["porta_1"] * 65),
                         ("un comando di un'altra fase", ["porta_1", "ancora"])):
        r = stato(a, A, pid, attivi)
        verifica(f"istantanea scartata: {nome} (e il gioco non ascolta finché non ne arriva una "
                 "buona)", r.get("_stato") == 400 and a.giochi.ascolto([A["id"]]) is None, str(r))
    stato(a, A, pid, ["porta_1", "porta_3"])
    a.eventi.clear()
    verifica("mossa: un comando non attivo non parte",
             a.giochi.comando(pid, A["id"], "porta_2") is False and not a.eventi)
    verifica("mossa: un comando inventato non parte",
             a.giochi.comando(pid, A["id"], "apri tutto") is False and not a.eventi)
    ok = a.giochi.comando(pid, A["id"], "porta_3", "Elena")
    e = [x for x in a.eventi if x[1] == "gioco"]
    verifica("mossa: al riquadro solo il nome del comando, il numero dell'istantanea e chi gioca",
             ok and len(e) == 1 and e[0][0] == A["id"] and e[0][2] == {
                 "partita": pid, "tipo": "comando",
                 "dati": {"comando": "porta_3", "n": _N[(pid, A["id"])],
                          "giocatore": "Elena"}}, str(e))
    r = stato(a, A, pid, [])
    verifica("comandi attivi vuoti (un'animazione, la fine): non ascolta, e la sveglia suona",
             r.get("ok") and a.giochi.ascolto([A["id"]]) is None and ev.is_set())
    stato(a, A, pid, ["porta_1"])
    r = a.pagina(A, {"partita": pid, "tipo": "chiuso"})
    verifica("«chiuso» dalla pagina (✕, Esc, chiudi il gioco): non ascolta più",
             r.get("ok") and a.giochi.ascolto([A["id"]]) is None)
    a.pagina(A, {"partita": pid, "tipo": "pronto"})
    _N[(pid, A["id"])] = 0                    # il motore riparte da capo
    stato(a, A, pid, ["inizia"], fase="preparazione")
    verifica("«Riapri» (un pronto nuovo, il motore da capo con n che riparte): ascolta di nuovo",
             list(a.giochi.ascolto([A["id"]])["comandi"]) == ["inizia"])
    a.giochi.partite[pid].posti[A["id"]].contatto -= GI.VIVO_S + 1
    verifica("senza segni dalla pagina da oltre VIVO_S (schermo spento): non ascolta",
             a.giochi.ascolto([A["id"]]) is None)
    a.pagina(A, {"partita": pid, "tipo": "battito", "secondi": 15})
    verifica("…il battito lo rimette", a.giochi.ascolto([A["id"]]) is not None)
    a.pagina(A, {"partita": pid, "tipo": "guasto", "motivo": "non risponde"})
    verifica("il cane da guardia lo chiude: non ascolta", a.giochi.ascolto([A["id"]]) is None)
    # Il nome di chi gioca solo se il manifesto lo chiede
    m, _ = file_gioco("porte")
    m["scheda"]["macchina"]["giocatore"] = False
    m["nome"], m["titolo"] = "porte_mute", "Porte senza nomi"
    a.installa("porte", manifesto={"nome": "porte_mute", "titolo": "Porte senza nomi",
                                   "scheda": m["scheda"]})
    out = a.chiama("est_porte_mute", {}, "Dario", schermo=A)
    a.pagina(A, {"partita": out["partita"], "tipo": "pronto"})
    stato(a, A, out["partita"], ["porta_1"])
    a.eventi.clear()
    a.giochi.comando(out["partita"], A["id"], "porta_1", "Elena")
    e = [x for x in a.eventi if x[1] == "gioco"]
    verifica("senza «giocatore» nella macchina la mossa non porta nessun nome",
             e and senza_n(e[0][2]["dati"]) == {"comando": "porta_1"}, str(e))
    # I comandi di un altro gioco (il tris ha le caselle, non le porte)
    out = a.chiama("est_tris", {}, "Dario", schermo=A)
    a.pagina(A, {"partita": out["partita"], "tipo": "pronto"})
    stato(a, A, out["partita"], ["casella_5"])
    r = stato(a, A, out["partita"], ["porta_1"])
    verifica("contrario: un comando di un altro gioco è rifiutato (l'istantanea è scartata)",
             r.get("_stato") == 400
             and a.giochi.partite[out["partita"]].posti[A["id"]].istantanea is None, str(r))
    # La partita di prova: i comandi arrivano (sono un ingresso), il ponte no
    mp, _ = file_gioco("porte")
    out = a.giochi.avvia_prova(a.chi("Dario", schermo=C), "porte", 1, valida(mp))
    pp = out["partita"]
    a.pagina(C, {"partita": pp, "tipo": "pronto"})
    r = stato(a, C, pp, ["porta_2"])
    a.eventi.clear()
    ok = a.giochi.comando(pp, C["id"], "porta_2", "Dario")
    rs = a.pagina(C, {"partita": pp, "tipo": "salva", "chiave": "x", "valore": 1})
    info = a.giochi.ascolto([C["id"]]) or {}
    verifica("partita di prova: comandi attivi e mossa a voce sì, ponte (salva) no",
             a.giochi.partite[pp].prova and r.get("ok") and ok and info.get("prova") is True
             and rs.get("_stato") == 403 and a.eventi, f"{r} {rs}")
    return a


# ═══════════════════════════ ciclo ═══════════════════════════

class AscoltoGioco(Ascolto):
    """L'ascolto finto: ricorda fino a quando è stato chiesto di ascoltare senza il nome e
    quando comincia la frase (adesso, o `inizio()`); `woke`: il nome sentito dalla wake word."""

    def __init__(self):
        self.chiamate, self.inizio, self.woke = [], None, False

    def attendi(self):
        pass

    def listen(self, wake, awake_until, seed=None, wakeup=None):
        self.chiamate.append(awake_until)
        self.started_at = self.ended_at = self.inizio() if self.inizio else time.monotonic()
        return np.zeros(16000, dtype=np.float32)


def nuovo_ciclo(a, sat, satellite_id, turni):
    cfg = a.cfg
    cfg.speaker_id_enabled = False
    cfg.barge_in_enabled = False
    cfg.debug_audio_dir = None
    cfg.uscita_controllo = False
    # Qui la strada dell'11/10 (il modello della voce con gioco_comando): il giudice di fase
    # (14/10) ha le sue prove in prova_gioco_stato.py
    cfg.giochi_giudice = False
    stt, voce, chi, cervello, persone = Whisper(), Voce(), ChiParla(), Cervello(), Persone()
    chi.current_speaker = "Dario"
    instr = types.SimpleNamespace(dopo_turno=lambda x: x, inizio_voce=lambda: None,
                                  persona=lambda *x: None, origine=lambda: {},
                                  annuncia_verso=lambda *x, **k: None,
                                  risposta_scritta=lambda *x: None)
    srv = Servizi(cfg, registry=persone, stt=stt, instradamento=instr, cortesia=Cortesia(),
                  turns=types.SimpleNamespace(write=lambda r: turni.append(dict(r))),
                  attiva_minori=lambda: False, giochi=a.giochi, satelliti=sat)
    annunci = types.SimpleNamespace(agenda=__import__("queue").Queue(), documenti=None,
                                    installazioni=None, lavori=None, estensioni=None)
    ascolto = AscoltoGioco()
    ctx = types.SimpleNamespace(gioco_turno=None)
    c = Ciclo(srv, corsie.Corsia(f"sat:{satellite_id}", satellite_id=satellite_id), ascolto,
              voce, chi, cervello, ctx, annunci, None, threading.Event())
    return c, stt, voce, cervello, ascolto


def prova_ciclo(tmp: Path):
    sezione("ciclo: la regola gioco_comando e la finestra senza nome")
    a = Ambiente(tmp)
    a.installa("porte")
    A, B = a.abbina("A", "studio"), a.abbina("B", "cucina")
    sat = a.hub.satelliti = Satelliti({7: Coll(id=7, schermo_id=A["id"], stanza="studio"),
                                       8: Coll(id=8, schermo_id=B["id"], stanza="cucina")})
    turni = []
    c, stt, voce, cervello, ascolto = nuovo_ciclo(a, sat, 7, turni)
    a.cfg.giochi_ascolto_s = 60.0

    def giro(frase, k=None):
        k = k or (c, stt, voce, cervello)
        # La finestra di sempre (followup_s dopo una risposta) è già finita: qui conta quella
        # del gioco
        k[0].awake_until = 0.0
        k[1].frasi.append(frase)
        n, m = len(k[2].detto), len(k[3].richieste)
        a.eventi.clear()
        k[0].giro()
        mosse = [x[2] for x in a.eventi if x[1] == "gioco" and x[2].get("tipo") == "comando"]
        return k[2].detto[n:], k[3].richieste[m:], mosse

    detto, chiesto, mosse = giro("Calliope, uno.")
    verifica("contrario: nessun gioco aperto → «Calliope, uno.» va al modello",
             chiesto and chiesto[0][0].startswith("uno") and not mosse
             and "gioco_comando" not in (c.rec or {}).get("regole", []), str(chiesto))
    out = a.chiama("est_porte", {}, "Dario", schermo=A)
    pid = out["partita"]
    a.pagina(A, {"partita": pid, "tipo": "pronto"})
    stato(a, A, pid, ["porta_1", "porta_2", "porta_3"])
    verifica("il gioco apre i comandi: la sveglia del ciclo suona", c.sveglia_gioco.is_set())
    detto, chiesto, mosse = giro("La porta due.")
    fino = ascolto.chiamate[-1]
    verifica("l'ascolto resta aperto senza il nome per giochi_ascolto_s (pallino «ascolto»)",
             fino > time.monotonic() + 50 and c.attesa_voce[0] == "ascolta",
             f"{fino - time.monotonic():.1f} s, {c.attesa_voce}")
    verifica("«La porta due.» senza il nome nella finestra del gioco: una mossa, senza il "
             "modello e senza parlare",
             [senza_n(m_["dati"]) for m_ in mosse] == [{"comando": "porta_2"}]
             and not chiesto and not detto and c.rec.get("esito") == "gioco_comando"
             and "gioco_comando" in c.rec.get("regole", []) and c.rec.get("testo") is None,
             f"{mosse} {chiesto} {detto} {c.rec}")
    ms = c.rec.get("gioco", {}).get("ms")
    verifica("latenza della mossa: da fine ascolto alla mossa, niente LLM",
             isinstance(ms, int) and ms < 200, f"{ms} ms (STT finto)")
    detto, chiesto, mosse = giro("Che ore sono?")
    verifica("senza il nome nella finestra del gioco una frase qualsiasi si ignora e non resta",
             not chiesto and not detto and not mosse and c.rec.get("esito") == "ignorato"
             and c.rec.get("testo") is None
             and "gioco_finestra_ignorata" in c.rec.get("regole", []), str(c.rec))
    detto, chiesto, mosse = giro("Apri la porta tre, per favore.")
    verifica("contrario: un comando dentro una frase più lunga, senza il nome → ignorata",
             not chiesto and not mosse and c.rec.get("esito") == "ignorato")
    detto, chiesto, mosse = giro("Calliope, apri la porta tre per favore.")
    contesto = chiesto[0][1] if chiesto else ""
    verifica("con il nome la frase lunga va al modello, con i comandi del gioco nel contesto "
             "e il gioco per gioco_comando",
             chiesto and not mosse and "Apri le porte" in (contesto or "")
             and "gioco_comando" in (contesto or "") and c.tool_ctx.gioco_turno
             and c.tool_ctx.gioco_turno["partita"] == pid, f"{chiesto}")
    detto, chiesto, mosse = giro("Calliope, la porta 1!")
    verifica("con il nome davanti e i numeri in cifre: mossa",
             [m_["dati"]["comando"] for m_ in mosse] == ["porta_1"] and not chiesto)
    stato(a, A, pid, ["porta_3"])
    detto, chiesto, mosse = giro("Due.")
    verifica("contrario: un comando non attivo senza il nome → ignorato, niente mossa",
             not mosse and not chiesto and c.rec.get("esito") == "ignorato")
    detto, chiesto, mosse = giro("Calliope, due.")
    verifica("contrario: un comando non attivo con il nome → al modello", chiesto and not mosse)
    cervello.has_pending = lambda: True
    detto, chiesto, mosse = giro("Calliope, tre.")
    del cervello.has_pending
    verifica("contrario: con una domanda di Calliope in sospeso la frase va al modello",
             chiesto and not mosse)
    fine = list(cervello.fine)
    stato(a, A, pid, ["ancora"], fase="fine")
    detto, chiesto, mosse = giro("Ricomincia.")
    verifica("«Ricomincia.» dentro il gioco: riavvia il gioco («ancora»), non la conversazione",
             [m_["dati"]["comando"] for m_ in mosse] == ["ancora"]
             and cervello.fine == fine)
    # Un altro satellite, con il suo schermo: il gioco è sullo schermo del primo
    k8 = nuovo_ciclo(a, sat, 8, turni)
    detto, chiesto, mosse = giro("Tre.", k8[:4])
    verifica("contrario: dal satellite della cucina «Tre.» senza nome non è una mossa (e non "
             "allunga l'ascolto)", not mosse and not chiesto and k8[4].chiamate[-1] < 1e9
             and k8[0].attesa_voce[0] == "dorme", str(k8[0].attesa_voce))
    detto, chiesto, mosse = giro("Calliope, tre.", k8[:4])
    verifica("contrario: dal satellite della cucina «Calliope, tre.» va al modello, niente "
             "mossa sul gioco dello studio", chiesto and not mosse)
    stato(a, A, pid, ["porta_3"])
    # Il tetto di tempo senza mosse: torna «dormo»
    a.cfg.giochi_ascolto_s = 0.3
    c.awake_until = 0.0
    c._gioco_segno = 0.0
    c.rec = None                     # l'ultimo turno è finito da tempo
    a.giochi.partite[pid].posti[A["id"]].segno = time.monotonic() - 1.0
    ascolto.inizio = lambda: time.monotonic()
    detto, chiesto, mosse = giro("Tre.")
    verifica("oltre il tetto senza mosse: «dormo», e «Tre.» senza nome si ignora come sempre",
             not mosse and c.attesa_voce[0] == "dorme" and c.rec.get("esito") == "ignorato"
             and "gioco_finestra_ignorata" not in c.rec.get("regole", []), str(c.rec))
    detto, chiesto, mosse = giro("Calliope, tre.")
    verifica("…con il nome la mossa vale ancora", [m_["dati"]["comando"] for m_ in mosse]
             == ["porta_3"])
    a.cfg.giochi_ascolto_s = 60.0
    # Il gioco chiuso
    a.pagina(A, {"partita": pid, "tipo": "chiuso"})
    c.awake_until = 0.0
    detto, chiesto, mosse = giro("Calliope, ricomincia.")
    verifica("contrario: gioco chiuso → «Calliope, ricomincia.» va avanti come sempre (non al "
             "gioco)", not mosse and c.attesa_voce[0] == "dorme")

    sezione("gioco_comando: il modello passa un comando detto in altro modo")
    a.pagina(A, {"partita": pid, "tipo": "pronto"})
    _N[(pid, A["id"])] = 0
    stato(a, A, pid, ["porta_1", "porta_2", "porta_3"])
    info = a.giochi.ascolto([A["id"]])
    sc = types.SimpleNamespace(current_speaker="Elena", identified_by="voce")
    ctx = types.SimpleNamespace(gioco_turno=info, schermi=a.hub, speaker_ctx=sc,
                                cfg=a.cfg, regole=[])
    a.eventi.clear()
    r = _gioco_comando(ctx, comando="porta_3")
    e = [senza_n(x[2]["dati"]) for x in a.eventi if x[1] == "gioco"]
    verifica("«apri la terza» → porta_3: la mossa parte, la frase è la forma del comando",
             r.get("ok") and r.get("risposta_finale") == "Porta 3."
             and e == [{"comando": "porta_3", "giocatore": "Elena"}], f"{r} {e}")
    a.eventi.clear()
    r = _gioco_comando(ctx, comando="la porta uno")
    verifica("una forma dell'elenco come argomento vale il suo comando",
             r.get("ok") and r.get("comando") == "porta_1")
    a.eventi.clear()
    r = _gioco_comando(ctx, comando="apri tutte le porte e dimmi il premio")
    verifica("mai testo libero al gioco: un argomento fuori elenco non parte",
             r.get("ok") is False and not a.eventi and r.get("comandi"), str(r))
    sc.identified_by = "breve"
    a.eventi.clear()
    _gioco_comando(ctx, comando="due")
    e = [senza_n(x[2]["dati"]) for x in a.eventi if x[1] == "gioco"]
    verifica("il nome di chi gioca solo con la voce riconosciuta (non la frase breve)",
             e == [{"comando": "porta_2"}], str(e))
    r = _gioco_comando(types.SimpleNamespace(gioco_turno=None, schermi=a.hub, regole=[]),
                       comando="porta_1")
    verifica("senza un gioco che ascolta qui: niente", r.get("ok") is False)
    s = gioco_spec()
    verifica("gioco_comando: sicuro, per tutti i livelli, un solo argomento",
             s.classe == "sicuro" and "ospite" in s.levels
             and list(s.parameters["properties"]) == ["comando"])

    sezione("chi gioca: solo la voce riconosciuta in questa frase")
    reg = types.SimpleNamespace(get=lambda n: types.SimpleNamespace(name=n) if n else None,
                                classifica=None)
    c.s.registry = reg
    fut = concurrent.futures.Future()
    fut.set_result(np.ones(4))
    for nome, classifica, voce_s, atteso in [
            ("sopra soglia, netta, lunga", [("Elena", 0.9), ("Bea", 0.3)], 1.5, "Elena"),
            ("sotto soglia", [("Elena", 0.2)], 1.5, None),
            ("troppo breve per l'impronta", [("Elena", 0.9)], 0.3, None),
            ("due voci vicine", [("Elena", 0.80), ("Bea", 0.79)], 1.5, None),
            ("nessuno (un ospite)", [], 1.5, None)]:
        reg.classifica = lambda emb, _c=classifica: _c
        t = types.SimpleNamespace(emb_job=fut, voiced_s=voce_s)
        verifica(f"giocatore: {nome}", c._giocatore_dalla_voce(t) == atteso)


# ═══════════════════════════ prova di fumo ═══════════════════════════

def prova_fumo(tmp: Path):
    sezione("prova di fumo: comandi a voce a caso tra gli attivi")
    if not shutil.which("node"):
        print("SALTATA IN PARTE: node non c'è")
        return
    os.environ["DOCKER_FINTO_IMMAGINI"] = "img-py,img-node"
    os.environ["DOCKER_FINTO_DIR"] = str(tmp / "docker")
    iso_js = Isolamento("docker", "finto", True, "", "img-node", FINTO)
    m, file = file_gioco("porte")

    def prova(nome, sost=None, manifesto=None):
        sb = Sandbox(tmp / nome, 30, 256, isolamento=Isolamento("docker", "finto", True, "",
                                                                 "img-py", FINTO),
                     linguaggi={"javascript": iso_js})
        for k, v in file.items():
            t = v.decode()
            for x, y in (sost or {}).items():
                t = t.replace(x, y)
            sb.scrivi(k, t)
        sb.scrivi("manifesto.json", json.dumps(manifesto or m))
        return sb.test()
    r = prova("buono")
    verifica("il gioco delle porte passa la prova di fumo con i comandi",
             r["passano"] and "ok prova di fumo" in r["uscita"], r["uscita"][-300:])
    # Dal 14/10 i comandi a voce li riceve il motore: una mossa che lancia la trova già
    # l'esploratore delle fasi, con il comando piatto e file:riga
    r = prova("rotto", {"registra(valore, giocatore);":
                        "if (valore === 3) throw new Error(\"porta tre rotta\");\n"
                        "        registra(valore, giocatore);"})
    verifica("una mossa che lancia: la prova di fumo lo trova e dice quale comando",
             not r["passano"] and "comando «porta_3»" in r["uscita"]
             and "porta tre rotta" in r["uscita"] and "logica.js:" in r["uscita"],
             r["uscita"][-400:])
    r = prova("fuori", {"turno: (d) => ({ porta: chiuse(d) }),":
                        "turno: (d) => ({ porta: chiuse(d).concat([4]) }),"})
    verifica("comandi attivi fuori da quelli dichiarati: la prova di fumo lo dice",
             not r["passano"] and "valori fuori da quelli dichiarati" in r["uscita"]
             and "[4]" in r["uscita"], r["uscita"][-400:])
    # 12/10 sera: un campo che la logica non dà, mostrato (il caso vero: l'esito annidato) →
    # «undefined» nel testo visibile
    r = prova("campo", {'turno: () => ({ titolo: "Quale porta apri?" }),':
                        'turno: (d) => ({ titolo: "Quale porta apri?", testo: "Premio " + d.premio.emoji }),'})
    verifica("un campo che non c'è mostrato a schermo («undefined»): la prova di fumo lo dice",
             not r["passano"] and "«undefined»" in r["uscita"]
             and "GIOCO.vista" in r["uscita"], r["uscita"][-400:])
    # Il nome di chi gioca (macchina.giocatore): con i comandi a voce della prova arriva «Ada»
    nome = {"registra(valore, giocatore);":
            "if (giocatore === \"Ada\") throw new Error(\"nome arrivato: \" + giocatore);\n"
            "        registra(valore, giocatore);"}
    r = prova("nome", nome)
    verifica("con «giocatore» il nome di chi gioca arriva alla mossa a voce",
             not r["passano"] and "nome arrivato: Ada" in r["uscita"], r["uscita"][-300:])
    senza = json.loads(json.dumps(m))
    senza["scheda"]["macchina"]["giocatore"] = False
    r = prova("senza_nome", nome, manifesto=senza)
    verifica("contrario: senza «giocatore» nessun nome alla mossa",
             r["passano"] and "ok prova di fumo" in r["uscita"], r["uscita"][-300:])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    radice = Path(tempfile.mkdtemp(prefix="calliope-gioco-voce-"))
    try:
        prova_manifesto()
        prova_server(radice / "server")
        prova_ciclo(radice / "ciclo")
        prova_fumo(radice / "fumo")
    finally:
        from calliope import minori as M
        for s in ("regole", "avvisi", "gioco", "richieste"):
            x = M._SERVIZIO.get(s)
            if x is not None:
                try:
                    x.close()
                except Exception:  # noqa: BLE001
                    pass
        shutil.rmtree(radice, ignore_errors=True)
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
