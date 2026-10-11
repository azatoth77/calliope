"""I comandi a voce di un gioco a secco (11/10/2026, richiesta approvata da Dario: «un gioco può
usare la voce come modalità di interazione»; calliope/gioco_voce.py, calliope/schermi/giochi.py,
calliope/ciclo.py, docs/aree/giochi.md).

- **manifesto**: la sezione `scheda.ascolta` validata (limiti, forme riservate, il nome di chi
  gioca solo senza rete), le parole per chi approva;
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


def sezione(nome):
    print(f"— {nome}  [{time.perf_counter() - T0:.1f}s]", flush=True)


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


# ═══════════════════════════ manifesto ═══════════════════════════

def prova_manifesto():
    sezione("manifesto: scheda.ascolta")
    m, _ = file_gioco("porte")
    mv = valida(m)
    a = mv["scheda"].get("ascolta") or {}
    verifica("il gioco «porte» è valido, puro, con quattro comandi e il nome di chi gioca",
             SC.e_gioco_puro(mv) and list(a.get("comandi") or {}) == ["uno", "due", "tre",
                                                                      "ricomincia"]
             and a.get("giocatore") is True, str(a))
    parole = permessi_in_parole(mv)
    verifica("chi approva sente che si gioca a voce", "si gioca anche a voce" in parole, parole)

    def errore(ascolta, **altro):
        mm = json.loads(json.dumps(m))
        mm["scheda"]["ascolta"] = ascolta
        mm["scheda"].update(altro)
        if altro.get("azioni"):
            mm["permessi"] = {"rete": {"host": ["api.esempio.it"]}}
        try:
            valida(mm)
            return None
        except ManifestoNonValido as e:
            return str(e)
    for nome, asc, altro in [
            ("chiave sconosciuta", {"comandi": {"uno": ["uno"]}, "testo": True}, {}),
            ("un'uscita come forma", {"comandi": {"via": ["esci"]}}, {}),
            ("«basta» come forma", {"comandi": {"via": ["basta"]}}, {}),
            ("forma troppo lunga", {"comandi": {"x": ["apri subito la porta numero uno"]}}, {}),
            ("la stessa forma per due comandi", {"comandi": {"a": ["uno"], "b": ["1"]}}, {}),
            ("comandi vuoti", {"comandi": {}}, {}),
            ("non un oggetto", ["uno"], {}),
            ("il nome di chi gioca con rete_leggi", {"comandi": {"uno": ["uno"]},
                                                     "giocatore": True},
             {"azioni": ["rete_leggi"]})]:
        e = errore(asc, **altro)
        verifica(f"rifiutato: {nome}", e is not None and "ascolta" in e, e or "")
    verifica("contrario: senza «ascolta» la scheda è come prima",
             "ascolta" not in valida(file_gioco("tris")[0])["scheda"])


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
    verifica("«pronto»: l'avvio dice i comandi dichiarati, e la sveglia della voce suona",
             r["avvio"].get("comandi") == ["uno", "due", "tre", "ricomincia"] and ev.is_set(),
             str(r.get("avvio")))
    info = a.giochi.ascolto([A["id"]])
    verifica("il gioco ascolta tutti i suoi comandi", info is not None
             and list(info["comandi"]) == ["uno", "due", "tre", "ricomincia"]
             and info["giocatore"] is True and info["schermo"] == A["id"], str(info))
    verifica("contrario: sullo schermo di un altro satellite niente",
             a.giochi.ascolto([B["id"]]) is None)
    ev.clear()
    r = a.pagina(A, {"partita": pid, "tipo": "comandi", "attivi": ["uno", "tre", "ricomincia"]})
    verifica("il riquadro sceglie un sottoinsieme dei comandi dichiarati",
             r.get("ok") and list(a.giochi.ascolto([A["id"]])["comandi"])
             == ["uno", "tre", "ricomincia"], str(r))
    for nome, attivi in (("un comando nuovo", ["uno", "quattro"]), ("un numero", [1]),
                         ("non un elenco", "uno"), ("troppi", ["uno"] * 65)):
        r = a.pagina(A, {"partita": pid, "tipo": "comandi", "attivi": attivi})
        verifica(f"rifiutato: {nome} (resta il sottoinsieme di prima)",
                 r.get("_stato") == 400 and list(a.giochi.ascolto([A["id"]])["comandi"])
                 == ["uno", "tre", "ricomincia"], str(r))
    a.eventi.clear()
    verifica("mossa: un comando non attivo non parte",
             a.giochi.comando(pid, A["id"], "due") is False and not a.eventi)
    verifica("mossa: un comando inventato non parte",
             a.giochi.comando(pid, A["id"], "apri tutto") is False and not a.eventi)
    ok = a.giochi.comando(pid, A["id"], "tre", "Elena")
    e = [x for x in a.eventi if x[1] == "gioco"]
    verifica("mossa: al riquadro solo il nome del comando e quello di chi gioca",
             ok and len(e) == 1 and e[0][0] == A["id"] and e[0][2] == {
                 "partita": pid, "tipo": "comando",
                 "dati": {"comando": "tre", "giocatore": "Elena"}}, str(e))
    r = a.pagina(A, {"partita": pid, "tipo": "comandi", "attivi": []})
    verifica("comandi attivi vuoti (un'animazione, la fine): non ascolta, e la sveglia suona",
             r.get("ok") and a.giochi.ascolto([A["id"]]) is None and ev.is_set())
    a.pagina(A, {"partita": pid, "tipo": "comandi", "attivi": ["uno"]})
    r = a.pagina(A, {"partita": pid, "tipo": "chiuso"})
    verifica("«chiuso» dalla pagina (✕, Esc, chiudi il gioco): non ascolta più",
             r.get("ok") and a.giochi.ascolto([A["id"]]) is None)
    a.pagina(A, {"partita": pid, "tipo": "pronto"})
    verifica("«Riapri» (un pronto nuovo): di nuovo tutti i comandi",
             len(a.giochi.ascolto([A["id"]])["comandi"]) == 4)
    a.giochi.partite[pid].posti[A["id"]].contatto -= GI.VIVO_S + 1
    verifica("senza segni dalla pagina da oltre VIVO_S (schermo spento): non ascolta",
             a.giochi.ascolto([A["id"]]) is None)
    a.pagina(A, {"partita": pid, "tipo": "battito", "secondi": 15})
    verifica("…il battito lo rimette", a.giochi.ascolto([A["id"]]) is not None)
    a.pagina(A, {"partita": pid, "tipo": "guasto", "motivo": "non risponde"})
    verifica("il cane da guardia lo chiude: non ascolta", a.giochi.ascolto([A["id"]]) is None)
    # Il nome di chi gioca solo se il manifesto lo chiede
    m, _ = file_gioco("porte")
    m["scheda"]["ascolta"]["giocatore"] = False
    m["nome"], m["titolo"] = "porte_mute", "Porte senza nomi"
    a.installa("porte", manifesto={"nome": "porte_mute", "titolo": "Porte senza nomi",
                                   "scheda": m["scheda"]})
    out = a.chiama("est_porte_mute", {}, "Dario", schermo=A)
    a.pagina(A, {"partita": out["partita"], "tipo": "pronto"})
    a.eventi.clear()
    a.giochi.comando(out["partita"], A["id"], "uno", "Elena")
    e = [x for x in a.eventi if x[1] == "gioco"]
    verifica("senza «giocatore» nel manifesto la mossa non porta nessun nome",
             e and e[0][2]["dati"] == {"comando": "uno"}, str(e))
    # Un gioco senza «ascolta»
    out = a.chiama("est_tris", {}, "Dario", schermo=A)
    a.pagina(A, {"partita": out["partita"], "tipo": "pronto"})
    r = a.pagina(A, {"partita": out["partita"], "tipo": "comandi", "attivi": []})
    verifica("un gioco senza comandi a voce: «comandi» rifiutato e niente ascolto",
             r.get("_stato") == 403 and all(i is None or i["partita"] != out["partita"]
                                            for i in [a.giochi.ascolto([A["id"]])]))
    # La partita di prova: i comandi arrivano (sono un ingresso), il ponte no
    mp, _ = file_gioco("porte")
    out = a.giochi.avvia_prova(a.chi("Dario", schermo=C), "porte", 1, valida(mp))
    pp = out["partita"]
    a.pagina(C, {"partita": pp, "tipo": "pronto"})
    r = a.pagina(C, {"partita": pp, "tipo": "comandi", "attivi": ["due"]})
    a.eventi.clear()
    ok = a.giochi.comando(pp, C["id"], "due", "Dario")
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
    verifica("il gioco apre i comandi: la sveglia del ciclo suona", c.sveglia_gioco.is_set())
    detto, chiesto, mosse = giro("La porta due.")
    fino = ascolto.chiamate[-1]
    verifica("l'ascolto resta aperto senza il nome per giochi_ascolto_s (pallino «ascolto»)",
             fino > time.monotonic() + 50 and c.attesa_voce[0] == "ascolta",
             f"{fino - time.monotonic():.1f} s, {c.attesa_voce}")
    verifica("«La porta due.» senza il nome nella finestra del gioco: una mossa, senza il "
             "modello e senza parlare",
             mosse == [{"partita": pid, "tipo": "comando", "dati": {"comando": "due"}}]
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
             [m_["dati"]["comando"] for m_ in mosse] == ["uno"] and not chiesto)
    a.pagina(A, {"partita": pid, "tipo": "comandi", "attivi": ["tre", "ricomincia"]})
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
    detto, chiesto, mosse = giro("Ricomincia.")
    verifica("«Ricomincia.» dentro il gioco: riavvia il gioco, non la conversazione",
             [m_["dati"]["comando"] for m_ in mosse] == ["ricomincia"]
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
             == ["tre"])
    a.cfg.giochi_ascolto_s = 60.0
    # Il gioco chiuso
    a.pagina(A, {"partita": pid, "tipo": "chiuso"})
    c.awake_until = 0.0
    detto, chiesto, mosse = giro("Calliope, ricomincia.")
    verifica("contrario: gioco chiuso → «Calliope, ricomincia.» va avanti come sempre (non al "
             "gioco)", not mosse and c.attesa_voce[0] == "dorme")

    sezione("gioco_comando: il modello passa un comando detto in altro modo")
    a.pagina(A, {"partita": pid, "tipo": "pronto"})
    info = a.giochi.ascolto([A["id"]])
    sc = types.SimpleNamespace(current_speaker="Elena", identified_by="voce")
    ctx = types.SimpleNamespace(gioco_turno=info, schermi=a.hub, speaker_ctx=sc,
                                cfg=a.cfg, regole=[])
    a.eventi.clear()
    r = _gioco_comando(ctx, comando="tre")
    e = [x[2]["dati"] for x in a.eventi if x[1] == "gioco"]
    verifica("«apri la terza» → tre: la mossa parte, la frase è la forma del comando",
             r.get("ok") and r.get("risposta_finale") == "Tre."
             and e == [{"comando": "tre", "giocatore": "Elena"}], f"{r} {e}")
    a.eventi.clear()
    r = _gioco_comando(ctx, comando="la porta uno")
    verifica("una forma dell'elenco come argomento vale il suo comando",
             r.get("ok") and r.get("comando") == "uno")
    a.eventi.clear()
    r = _gioco_comando(ctx, comando="apri tutte le porte e dimmi il premio")
    verifica("mai testo libero al gioco: un argomento fuori elenco non parte",
             r.get("ok") is False and not a.eventi and r.get("comandi"), str(r))
    sc.identified_by = "breve"
    a.eventi.clear()
    _gioco_comando(ctx, comando="due")
    e = [x[2]["dati"] for x in a.eventi if x[1] == "gioco"]
    verifica("il nome di chi gioca solo con la voce riconosciuta (non la frase breve)",
             e == [{"comando": "due"}], str(e))
    r = _gioco_comando(types.SimpleNamespace(gioco_turno=None, schermi=a.hub, regole=[]),
                       comando="uno")
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
    r = prova("rotto", {"calliope.quandoComando(sicuro((m) => {":
                        "calliope.quandoComando(((m) => { if (m.comando === \"tre\") "
                        "throw new Error(\"porta tre rotta\");"})
    verifica("un gestore dei comandi che lancia: la prova di fumo lo trova e dice quale comando",
             not r["passano"] and "comando «tre»" in r["uscita"]
             and "porta tre rotta" in r["uscita"], r["uscita"][-400:])
    r = prova("fuori", {"calliope.comandiAttivi(comandiAdesso(stato));":
                        "calliope.comandiAttivi(comandiAdesso(stato).concat([\"quattro\"]));"})
    verifica("comandiAttivi con un comando non dichiarato: la prova di fumo lo dice",
             not r["passano"] and "non dichiarati" in r["uscita"] and "quattro" in r["uscita"],
             r["uscita"][-400:])
    senza = json.loads(json.dumps(m))
    del senza["scheda"]["ascolta"]
    r = prova("senza_ascolta", manifesto=senza)
    verifica("comandiAttivi senza «ascolta» nel manifesto: la prova di fumo lo dice",
             not r["passano"] and "non ha «ascolta.comandi»" in r["uscita"], r["uscita"][-300:])
    r = prova("senza", {"calliope.comandiAttivi(comandiAdesso(stato));": ""}, manifesto=senza)
    verifica("contrario: senza «ascolta» nessun comando (e il gioco si gioca con i tocchi)",
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
