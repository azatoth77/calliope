"""
Prova a secco delle conversazioni per persona e dei satelliti insieme (06/10/2026,
calliope/corsie.py; rapporto docs/ricerche/2026-10-06-conversazione-persona.md).

    python prove/prova_corsie.py

Senza modello, audio né rete: Brain con un backend finto che risponde guardando la storia.
  1. scelta della conversazione: voce riconosciuta (sua da ogni satellite), frase breve e zona
     grigia (solo dove ha parlato), scritto, ospiti per satellite;
  2. Brain con il registro: la conversazione di Dario passa dal portatile al telefono, Bianca e
     l'ospite non la vedono, il numero dei turni è della conversazione;
  3. azione in sospeso: un «sì» breve su un altro satellite non la raccoglie, la voce sì;
  4. una conversazione usata da una corsia alla volta; doppioni tra satelliti;
  5. risposte in parallelo (Varco): limite, frase d'attesa una volta, ordine d'arrivo;
  6. voce occupata contata per corsia (arbitro, compressione);
  7. smistatore degli annunci e delle frasi scritte; Ciclo (stato per corsia);
  8. chiusura delle conversazioni ferme e ripresa dopo un riavvio (anche quella «casa»);
  9. compressione per conversazione: una corsia non butta quella pronta di un'altra;
 10. server dei satelliti con tutti insieme: eventi per satellite, `attivo` della corsia,
     prendi/lascia/presta che non tolgono il posto a nessuno.
"""
import json
import os
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from calliope import corsie  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.conversazione import Conversazione  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402

errori = 0


def verifica(nome, cond, extra=""):
    global errori
    if not cond:
        errori += 1
    print(("ok  " if cond else "ERR ") + nome + (f"  ({extra})" if extra and not cond else ""))


# ───────────────────────── strumenti ─────────────────────────
class Backend:
    """Risponde guardando la storia: «come si chiama il mio gatto?» → il nome detto prima in
    questa conversazione, o «Non lo so.»"""

    def __init__(self):
        self.visti = []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        utente = [m.get("content") or "" for m in messages if m.get("role") == "user"]
        domanda = utente[-1].lower() if utente else ""
        if "gatto" in domanda and "?" in domanda:
            nome = next((u.split("si chiama")[-1].strip(" .") for u in utente[:-1]
                         if "gatto si chiama" in u), None)
            yield ("text", f"Si chiama {nome}." if nome else "Non lo so.")
            return
        yield ("text", "Va bene.")


class Voci:
    class P:
        def __init__(self, pid, nome, admin=False):
            self.id, self.name, self.admin = pid, nome, admin
            self.preferred_voice = self.preferred_tone = None

    def __init__(self):
        self.users = {"Dario": self.P("dario-id", "Dario", True),
                      "Bianca": self.P("bianca-id", "Bianca")}

    def get(self, n):
        return self.users.get(n)


class Chi:
    """Lo SpeakerContext di una corsia (solo ciò che Brain legge)."""

    def __init__(self):
        self.current_speaker, self.current_level, self.identified_by = None, "ospite", None
        self.sfida = None


def cfg_prova(**k):
    cfg = Config()
    cfg.storia_inattiva_s = 300.0
    for a, v in k.items():
        setattr(cfg, a, v)
    return cfg


def corsia_finta(chiave, sat_id, registro, varco=None):
    c = corsie.Corsia(chiave, satellite_id=sat_id, nome=chiave, registro=registro, varco=varco)
    b = Brain.__new__(Brain)
    b.cfg, b.tools = registro.cfg, build_registry()
    chi = Chi()
    b.tool_ctx = type("T", (), {"speaker_ctx": chi, "speakers": VOCI})()
    b.backend = Backend()
    b.conversazioni, b.satellite = registro, chiave
    c.brain, c.speaker_ctx = b, chi
    return c


VOCI = Voci()


def parla(c, testo, nome=None, how=None, in_session=False):
    """Un turno sulla corsia `c`: chi parla, scelta della conversazione, risposta."""
    chi = c.speaker_ctx
    chi.current_speaker = nome
    chi.identified_by = how
    chi.current_level = ("amministra" if nome == "Dario" else "familiare") if nome else "ospite"
    pid = VOCI.get(nome).id if nome else None
    rec = {}
    if not c.turno(c.brain, nome, how, in_session, testo, rec, persona_id=pid):
        return None, rec
    detto = "".join(c.brain.stream_reply(testo, chi.current_level))
    c.fine_turno()
    return detto, rec


# ───────────────────────── 1. scelta ─────────────────────────
def prova_scelta():
    reg = corsie.RegistroConversazioni(cfg_prova())
    a = corsie.Corsia("sat:1", 1, registro=reg)
    b = corsie.Corsia("sat:2", 2, registro=reg)
    c1, come = reg.scegli(a, "dario-id", "voce", False)
    a.conv = c1
    verifica("voce riconosciuta: la conversazione della persona",
             c1.chiave == "persona:dario-id" and come == "persona", (c1.chiave, come))
    c2, come = reg.scegli(b, "dario-id", "voce", False)
    verifica("voce riconosciuta su un altro satellite: la stessa", c2 is c1, come)
    c3, come = reg.scegli(a, "dario-id", "breve", True)
    verifica("frase breve nella finestra, sul satellite dove ha parlato: continua",
             c3 is c1 and come == "continua", come)
    c4, come = reg.scegli(b, "dario-id", "breve", True)
    verifica("frase breve su un satellite dove non ha parlato: anonima, non la sua",
             c4 is not c1 and c4.chiave == "ospite:sat:2" and come == "anonima", c4.chiave)
    c5, come = reg.scegli(a, "dario-id", "breve", False)
    verifica("frase breve fuori dalla finestra: anonima", c5.chiave == "ospite:sat:1", come)
    c6, come = reg.scegli(a, "dario-id", "conversazione", True)
    verifica("zona grigia dove ha parlato: continua", c6 is c1 and come == "continua", come)
    c7, _ = reg.scegli(b, "dario-id", "conversazione", True)
    verifica("zona grigia altrove: anonima", c7.chiave == "ospite:sat:2")
    c8, come = reg.scegli(b, "dario-id", "schermo", True)
    verifica("scritto dallo schermo personale con la conversazione aperta: la sua",
             c8 is c1 and come == "schermo", come)
    c9, come = reg.scegli(b, "bianca-id", "schermo", True)
    verifica("scritto senza una conversazione sua: anonima (lo scritto non la apre)",
             c9.chiave == "ospite:sat:2" and reg.di_persona("bianca-id") is None, c9.chiave)
    o1, _ = reg.scegli(a, None, None, True)
    o2, _ = reg.scegli(b, None, None, True)
    verifica("ospiti: una conversazione per satellite, mai condivisa",
             o1.chiave == "ospite:sat:1" and o2.chiave == "ospite:sat:2" and o1 is not o2)
    o3, _ = reg.scegli(a, None, None, True)
    verifica("ospite di nuovo sullo stesso satellite: la stessa", o3 is o1)


# ───────────────────────── 2. Brain con il registro ─────────────────────────
def prova_brain():
    # Senza doppioni: qui le frasi uguali da due satelliti sono persone diverse, di seguito
    reg = corsie.RegistroConversazioni(cfg_prova(conversazione_doppione_s=0.0))
    port = corsia_finta("sat:1", 1, reg)
    tel = corsia_finta("sat:2", 2, reg)
    parla(port, "Calliope, il mio gatto si chiama Micio.", "Dario", "voce")
    detto, rec = parla(tel, "Calliope, come si chiama il mio gatto?", "Dario", "voce")
    verifica("comincio al portatile, continuo dal telefono: la storia viaggia con la persona",
             detto == "Si chiama Micio.", detto)
    verifica("registro dei turni: conversazione ripresa da un altro satellite",
             rec.get("conversazione", {}).get("come") == "ripresa", rec)
    detto, _ = parla(tel, "Come si chiama il mio gatto?", "Bianca", "voce")
    verifica("Bianca sullo stesso telefono: la sua conversazione, niente gatto di Dario",
             detto == "Non lo so.", detto)
    detto, _ = parla(port, "Come si chiama il mio gatto?", None, None, in_session=True)
    verifica("un ospite sul portatile: niente gatto di Dario", detto == "Non lo so.", detto)
    detto, _ = parla(port, "E come si chiama il mio gatto?", "Dario", "voce")
    verifica("Dario torna dopo l'ospite: la sua conversazione c'è ancora (non chiusa)",
             detto == "Si chiama Micio.", detto)
    conv = reg.di_persona("dario-id")
    verifica("numero dei turni della conversazione, non del satellite",
             conv.turn_number == 3 and port.brain.turn_number == 3, conv.turn_number)
    # «esci» dal telefono: la conversazione di Dario si chiude ovunque, e quella dopo continua
    # a contare i turni (una proposta di prima non diventa «la risposta precedente»)
    tel.turno(tel.brain, "Dario", "voce", False, "", None, persona_id="dario-id")
    tel.brain.end_conversation("dormi")
    tel.fine_turno()
    nuova = reg.di_persona("dario-id")
    verifica("«esci»: al posto della conversazione chiusa una nuova, il numero continua",
             nuova is not conv and not nuova.history and nuova.turn_number == 3,
             (nuova is conv, len(nuova.history), nuova.turn_number))
    detto, _ = parla(port, "Come si chiama il mio gatto?", "Dario", "voce")
    verifica("dopo «esci» la conversazione riparte da capo anche sull'altro satellite",
             detto == "Non lo so.", detto)


# ───────────────────────── 3. azione in sospeso ─────────────────────────
def prova_sospeso():
    reg = corsie.RegistroConversazioni(cfg_prova(conversazione_doppione_s=0.0))
    port = corsia_finta("sat:1", 1, reg)
    tel = corsia_finta("sat:2", 2, reg)
    parla(port, "Calliope, apri il preventivo.", "Dario", "voce")
    port.brain.set_pending({"tool": "pc_apri_file", "argomenti": {"risultato": 1},
                            "domanda": "Lo apro?"})
    conv = reg.di_persona("dario-id")
    verifica("la proposta ricorda il satellite dove è nata",
             (conv.pending or {}).get("satellite") == "sat:1", conv.pending)
    # Sul telefono la frase breve di Dario: la corsia del telefono ha la sua conversazione
    # (Dario ci aveva parlato con la voce), ma la proposta è nata sul portatile
    tel.conv = conv
    tel.speaker_ctx.current_speaker, tel.speaker_ctx.identified_by = "Dario", "breve"
    tel.turno(tel.brain, "Dario", "breve", True, "Sì.", None, persona_id="dario-id")
    tel.brain.last_rules = []
    msg = tel.brain._take_pending()
    verifica("«sì» breve su un altro satellite: non raccoglie la proposta nata altrove",
             msg is None and "sospeso_altro_satellite" in tel.brain.last_rules
             and conv.pending is not None, tel.brain.last_rules)
    tel.fine_turno()
    port.speaker_ctx.current_speaker, port.speaker_ctx.identified_by = "Dario", "breve"
    port.turno(port.brain, "Dario", "breve", True, "Sì.", None, persona_id="dario-id")
    msg = port.brain._take_pending()
    verifica("«sì» breve sul satellite dove è nata: la raccoglie", bool(msg))
    port.fine_turno()
    # Con la voce riconosciuta anche dall'altro satellite
    tel.speaker_ctx.identified_by = "voce"
    tel.turno(tel.brain, "Dario", "voce", False, "Sì, aprilo pure.", None,
              persona_id="dario-id")
    msg = tel.brain._take_pending()
    verifica("«sì» con la voce riconosciuta da un altro satellite: vale", bool(msg))
    tel.fine_turno()


def prova_scaduta_sospeso():
    """07/10 pomeriggio, caso vero della DGX: «Fai una ricerca…» dopo una pausa lunga (la
    conversazione si chiude per tempo all'inizio del turno, conversazione_scaduta) →
    «…Procedo?»; poi «Sì, grazie.» breve: finiva nella conversazione anonima del satellite
    (la corsia era rimasta sulla conversazione chiusa), senza la proposta, e il modello
    rispondeva «Prego!»."""
    reg = corsie.RegistroConversazioni(cfg_prova(conversazione_doppione_s=0.0))
    sat = corsia_finta("sat:1", 1, reg)
    parla(sat, "Calliope, il mio gatto si chiama Micio.", "Dario", "voce")
    vecchia = reg.di_persona("dario-id")
    vecchia.last_turn_at = time.monotonic() - 1000          # oltre storia_inattiva_s
    chi = sat.speaker_ctx
    chi.current_speaker, chi.identified_by, chi.current_level = "Dario", "voce", "amministra"
    testo = "Calliope, fai una ricerca sui pannelli solari."
    sat.turno(sat.brain, "Dario", "voce", False, testo, {}, persona_id="dario-id")
    "".join(sat.brain.stream_reply(testo, "amministra"))
    sat.brain.set_pending({"tool": "lavoro_affida", "argomenti": {"proposta": "L1"},
                           "domanda": "Procedo?"})
    sat.fine_turno()
    nuova = reg.di_persona("dario-id")
    verifica("conversazione scaduta all'inizio del turno: al suo posto una nuova",
             nuova is not vecchia and "conversazione_scaduta" in sat.brain.last_rules,
             sat.brain.last_rules)
    verifica("la corsia segue la conversazione nuova (non resta su quella chiusa)",
             sat.conv is nuova)
    rec = {}
    chi.identified_by, chi.current_level = "breve", "familiare"
    sat.turno(sat.brain, "Dario", "breve", True, "Sì, grazie.", rec, persona_id="dario-id")
    verifica("«Sì, grazie.» breve subito dopo: continua la sua conversazione, non anonima",
             rec.get("conversazione", {}).get("come") == "continua", rec.get("conversazione"))
    verifica("… e la proposta «Procedo?» c'è", bool(sat.brain._take_pending()))
    sat.fine_turno()
    # Contrario: un ospite (voce non riconosciuta) nella stessa finestra resta anonimo
    rec = {}
    chi.current_speaker, chi.identified_by, chi.current_level = None, None, "ospite"
    sat.turno(sat.brain, None, None, True, "Sì, grazie.", rec)
    verifica("contrario: un ospite nella stessa finestra resta nella conversazione anonima",
             rec.get("conversazione", {}).get("come") == "anonima"
             and not sat.brain._take_pending(), rec.get("conversazione"))
    sat.fine_turno()


# ───────────────────────── 4. uso e doppioni ─────────────────────────
def prova_uso_doppioni():
    reg = corsie.RegistroConversazioni(cfg_prova(conversazione_doppione_s=2.0))
    a = corsie.Corsia("sat:1", 1, registro=reg)
    b = corsie.Corsia("sat:2", 2, registro=reg)
    c, _ = reg.scegli(a, "dario-id", "voce", False)
    reg.occupa(c, a)
    preso = []

    def altra():
        preso.append(reg.occupa(c, b))
    t = threading.Thread(target=altra)
    t0 = time.monotonic()
    t.start()
    time.sleep(0.3)
    verifica("la stessa conversazione su un'altra corsia aspetta la fine del turno",
             not preso)
    reg.libera(c, a)
    t.join(3)
    verifica("…e la prende appena è libera", preso == [c], f"{time.monotonic() - t0:.2f} s")
    reg.libera(c, b)
    ora = 1000.0
    verifica("frase nuova: non è un doppione",
             reg.doppione("sat:1", "Calliope, che ore sono?", ora) is False)
    verifica("la stessa frase da un altro satellite subito dopo: doppione",
             reg.doppione("sat:2", "Calliope che ore sono", ora + 0.6) is True)
    verifica("quasi uguale (trascrizione diversa): doppione",
             reg.doppione("sat:2", "Calliope, che ora sono?", ora + 0.8) is True)
    verifica("dallo stesso satellite: non è un doppione (la persona ripete)",
             reg.doppione("sat:1", "Calliope, che ore sono?", ora + 1.0) is False)
    verifica("da un altro satellite dopo la finestra: non è un doppione",
             reg.doppione("sat:2", "Calliope, che ore sono?", ora + 3.5) is False)
    verifica("un'altra frase insieme: non è un doppione",
             reg.doppione("sat:1", "Calliope, accendi la luce in cucina.", ora + 3.6) is False)
    import numpy as np
    a_, b_ = np.zeros(4, np.float32), np.zeros(4, np.float32)
    a_[0], b_[1] = 1.0, 1.0
    verifica("la stessa frase da un'altra stanza con un'altra voce: non è un doppione",
             reg.doppione("sat:1", "Calliope, come si chiama il mio gatto?", ora + 10,
                          impronta=a_) is False
             and reg.doppione("sat:2", "Calliope, come si chiama il mio gatto?", ora + 10.5,
                              impronta=b_) is False)
    verifica("…con la stessa voce (due microfoni, una persona): doppione",
             reg.doppione("sat:3", "Calliope come si chiama il mio gatto", ora + 11,
                          impronta=a_ * 0.9 + b_ * 0.1) is True)
    reg2 = corsie.RegistroConversazioni(cfg_prova(conversazione_doppione_s=0.0))
    reg2.doppione("sat:1", "ciao", 1.0)
    verifica("conversazione_doppione_s 0: mai doppioni", not reg2.doppione("sat:2", "ciao", 1.1))


# ───────────────────────── 5. varco ─────────────────────────
def prova_varco():
    v = corsie.Varco(2)
    v.entra()
    v.entra()
    attese, ordine = [], []

    def dopo(nome):
        s = v.entra(lambda: attese.append(nome))
        ordine.append(nome)
        time.sleep(0.05)
        v.esci()
        return s
    t3 = threading.Thread(target=dopo, args=("terza",))
    t3.start()
    time.sleep(0.15)
    t4 = threading.Thread(target=dopo, args=("quarta",))
    t4.start()
    time.sleep(0.15)
    verifica("oltre il limite: la frase d'attesa, una volta per chi aspetta",
             attese == ["terza", "quarta"] and not ordine, (attese, ordine))
    v.esci()
    t3.join(2)
    v.esci()
    t4.join(2)
    verifica("in ordine d'arrivo", ordine == ["terza", "quarta"], ordine)
    verifica("mai più di 2 insieme", v.massimo == 2 and v.attivi == 0, (v.massimo, v.attivi))
    v0 = corsie.Varco(0)
    for _ in range(5):
        v0.entra(lambda: attese.append("x"))
    verifica("limite 0: nessun limite", v0.attivi == 5 and "x" not in attese)
    # Corsia: esci una volta sola anche se chiamata due volte (fine_turno dopo un errore)
    v1 = corsie.Varco(1)
    c = corsie.Corsia("sat:1", 1, varco=v1)
    c.entra_llm()
    c.esci_llm()
    c.fine_turno()
    verifica("la corsia esce dal varco una volta sola", v1.attivi == 0, v1.attivi)


# ───────────────────────── 6. voce occupata ─────────────────────────
def prova_condivisa():
    stato = []
    occ, lib = corsie.condivisa(lambda: stato.append("occupata"),
                                lambda *a: stato.append("libera"))
    fatto = threading.Event()

    def corsia_b():
        occ()
        fatto.wait(2)
        lib()
    occ()                              # corsia A (questo thread)
    t = threading.Thread(target=corsia_b)
    t.start()
    time.sleep(0.1)
    lib()                              # A ha finito, B parla ancora
    verifica("una corsia finisce mentre l'altra parla: la voce resta occupata",
             "libera" not in stato, stato)
    fatto.set()
    t.join(2)
    verifica("libera quando nessuna corsia la tiene", stato[-1] == "libera", stato)


# ───────────────────────── 7. smistatore e clona ─────────────────────────
def prova_smistatore():
    import queue
    agenda, scritti = queue.Queue(), queue.Queue()
    collegati = {"sat:1": True, "sat:2": True}
    s = corsie.Smistatore({"agenda": (agenda, lambda it: it.get("dove")),
                           "scritti": (scritti, lambda it: it.get("dove"))},
                          disponibile=lambda k: collegati.get(k, False))
    a, b = corsie.Corsia("sat:1", 1), corsie.Corsia("sat:2", 2)
    s.corsie = {"sat:1": a, "sat:2": b}
    agenda.put({"id": 1, "dove": "sat:2"})
    agenda.put({"id": 2, "dove": None})
    s.sveglia()
    verifica("sveglia: le corsie che hanno qualcosa (tutte, per l'annuncio senza origine)",
             a.sveglia.is_set() and b.sveglia.is_set())
    va, vb = s.vista("agenda", a), s.vista("agenda", b)
    verifica("il portatile prende solo ciò che non è del telefono",
             va.get_nowait()["id"] == 2 and va.empty())
    verifica("il telefono prende il suo", vb.get_nowait()["id"] == 1 and vb.empty())
    agenda.put({"id": 3, "dove": "sat:2"})
    collegati["sat:2"] = False
    verifica("satellite scollegato: il suo annuncio va a un altro",
             not va.empty() and va.get_nowait()["id"] == 3)
    collegati["sat:2"] = True
    vb.put({"id": 4})
    verifica("rinviato: torna alla stessa corsia", va.empty() and s.prendi("agenda", "sat:2")
             == {"id": 4})
    scritti.put({"testo": "ciao", "dove": "sat:1"})
    verifica("frase scritta dal telefono del portatile: alla sua corsia",
             s.vista("scritti", b).prendi() is None
             and s.vista("scritti", a).prendi()["testo"] == "ciao")
    verifica("fonte assente: niente vista", s.vista("altro", a) is None)


def prova_ciclo():
    """Il ciclo di ogni corsia è un oggetto (06/10, P8): stato suo, servizi condivisi, nessuna
    chiusura copiata."""
    from calliope.ciclo import Ciclo, Servizi
    srv = Servizi(cfg_prova())
    a = Ciclo(srv, corsie.Corsia("sat:1", 1), None, None, None, None, None, None, None,
              threading.Event())
    b = Ciclo(srv, corsie.Corsia("sat:2", 2), None, None, None, None, None, None, None,
              threading.Event())
    a.rec, a.awake_until = {}, 5.0
    a.rule("prova")
    a.enroll_reminded.add("Bianca")
    verifica("ciclo: ogni corsia ha il suo stato (turno, finestra, promemoria)",
             a.rec == {"regole": ["prova"]} and b.rec is None and b.awake_until == 0.0
             and not b.enroll_reminded and a.s is b.s)
    srv.enroll_pending = True
    verifica("ciclo: i servizi sono condivisi (primo avvio visto da tutte)",
             a.s.enroll_pending and b.s.enroll_pending)
    import pathlib
    sorgenti = "".join(f.read_text(encoding="utf-8") for f in
                       (pathlib.Path(corsie.__file__).parent).glob("*.py"))
    verifica("niente più chiusure copiate (corsie.clona, types.CellType)",
             not hasattr(corsie, "clona") and "CellType" not in sorgenti)


def prova_voce_per_corsia():
    """Lo stato della voce sugli schermi per corsia (06/10, P9): due satelliti in stanze
    diverse, ognuno con il suo VAD e la sua voce in uscita (callback che girano in altri
    thread). Prima i callback erano quelli della corsia locale, con un solo «stato in attesa»
    per tutti: lo studio che pensa e la cucina che dorme si sovrascrivevano."""
    from calliope.ciclo import Ciclo, Servizi

    class Hub:
        def __init__(self):
            self.v = []

        def voce(self, stato, fino=None, stanza=None, sorgente=None):
            self.v.append((stanza, stato))
            self.sorgenti = getattr(self, "sorgenti", []) + [sorgente]

    class Satelliti:
        def __init__(self):
            self.c = {1: types.SimpleNamespace(stanza="studio"),
                      2: types.SimpleNamespace(stanza="cucina")}

        def per_id(self, sid):
            return self.c.get(sid)

    hub, arbitro = Hub(), []
    srv = Servizi(cfg_prova(), schermi=hub, satelliti=Satelliti())

    def nuova(sid):
        lst = types.SimpleNamespace(on_speech_start=lambda: arbitro.append(("occupa", sid)),
                                    on_speech_end=lambda: arbitro.append(("libera", sid)))
        sp = types.SimpleNamespace(on_parla=None)
        c = Ciclo(srv, corsie.Corsia(f"sat:{sid}", sid), lst, sp, None, None, None, None, None,
                  threading.Event())
        return c, lst, sp
    (a, la, sa), (b, lb, sb) = nuova(1), nuova(2)
    a.voce("pensa")                                    # lo studio pensa (thread della corsia)
    lb.on_speech_start()                               # in cucina qualcuno comincia a parlare
    sb.on_parla()                                      # la cucina risponde (riproduzione)
    b.attesa_voce[:] = ["dorme", None]
    lb.on_speech_end()                                 # in cucina una frase buttata: dorme
    sa.on_parla()                                      # lo studio parla
    verifica("voce per corsia: ogni satellite manda il suo stato alla sua stanza",
             hub.v == [("studio", "pensa"), ("cucina", "ascolta"), ("cucina", "parla"),
                       ("cucina", "dorme"), ("studio", "parla")], str(hub.v))
    verifica("voce per corsia: ogni satellite manda il suo stato come sorgente (Q9)",
             hub.sorgenti == ["sat:1", "sat:2", "sat:2", "sat:2", "sat:1"], str(hub.sorgenti))
    verifica("voce per corsia: lo stato in attesa è della corsia (lo studio non dorme)",
             a.attesa_voce == ["dorme", None] and a.attesa_voce is not b.attesa_voce)
    verifica("voce per corsia: i callback di prima (arbitro, compressione) restano",
             arbitro == [("occupa", 2), ("libera", 2)], str(arbitro))
    del srv.satelliti.c[2]
    n = len(hub.v)
    lb.on_speech_start()
    verifica("voce per corsia: satellite scollegato, niente agli schermi",
             len(hub.v) == n and arbitro[-1] == ("occupa", 2))
    loc = Ciclo(srv, corsie.Corsia("locale"), types.SimpleNamespace(on_speech_start=None,
                                                                    on_speech_end=None),
                types.SimpleNamespace(on_parla=None), None, None, None, None, None,
                threading.Event())
    loc.voce("pensa")
    verifica("voce per corsia: la corsia locale vale come prima (il microfono che ascolta)",
             hub.v[-1] == (None, "pensa"))
    # Q9: il satellite che se ne va toglie il suo stato dagli schermi (main.Corsie)
    from calliope.main import Corsie
    via = []
    finto = types.SimpleNamespace(a=types.SimpleNamespace(s=types.SimpleNamespace(
        schermi=types.SimpleNamespace(voce_via=via.append))))
    presenti = {"sat:1", "sat:2"}
    Corsie._voce_di_chi_va(finto, presenti, {"sat:1"})
    Corsie._voce_di_chi_va(finto, presenti, {"sat:1", "sat:2"})
    verifica("voce per corsia: il satellite che se ne va toglie il suo stato (una volta)",
             via == ["sat:2"] and presenti == {"sat:1", "sat:2"}, f"{via} {presenti}")


# ───────────────────────── 8. chiusura e ripresa ─────────────────────────
def prova_pulizia_ripresa():
    reg = corsie.RegistroConversazioni(cfg_prova(storia_inattiva_s=60.0,
                                                 conversazione_doppione_s=0.0))
    port = corsia_finta("sat:1", 1, reg)
    parla(port, "Calliope, il mio gatto si chiama Micio.", "Dario", "voce")
    conv = reg.di_persona("dario-id")
    chiuse = []
    port.brain.end_conversation = lambda motivo="fine", _o=port.brain.end_conversation: (
        chiuse.append(motivo), _o(motivo))[-1]
    n = reg.pulisci(port.brain, ora=time.monotonic() + 30, forza=True)
    verifica("ferma da meno di storia_inattiva_s: resta", n == 0 and not chiuse)
    reg.occupa(conv, port)
    n = reg.pulisci(port.brain, ora=time.monotonic() + 120, forza=True)
    verifica("in uso: resta anche se vecchia", n == 0)
    reg.libera(conv, port)
    n = reg.pulisci(port.brain, ora=time.monotonic() + 120, forza=True)
    verifica("ferma da più di storia_inattiva_s: chiusa (archivio, riassunto)",
             n == 1 and chiuse == ["conversazione_scaduta"]
             and reg.di_persona("dario-id") is not conv
             and port.brain.conv is reg.di_persona("dario-id")
             and not port.brain.conv.history, chiuse)
    # Ripresa dopo un riavvio: anche la conversazione «casa» salvata da una versione di prima
    from calliope.conversazioni import ArchivioConversazioni
    with tempfile.TemporaryDirectory(prefix="calliope-corsie-",
                                     ignore_cleanup_errors=True) as d:
        a = ArchivioConversazioni(os.path.join(d, "c.db"))
        vecchia = Conversazione("casa")
        vecchia.owner, vecchia.last_turn_at = "dario-id", time.monotonic()
        vecchia.history = [{"role": "user", "content": "il mio gatto si chiama Micio"},
                           {"role": "assistant", "content": "Bel nome."}]
        a.salva_corrente(vecchia)
        osp = Conversazione("ospite:sat:2")
        osp.owner, osp.last_turn_at = None, time.monotonic()
        osp.history = [{"role": "user", "content": "ciao"}]
        a.salva_corrente(osp)
        vuota = Conversazione("persona:bianca-id")
        vuota.last_turn_at = time.monotonic()
        a.salva_corrente(vuota)
        a.attendi()
        reg2 = corsie.RegistroConversazioni(cfg_prova())
        n = reg2.riprendi(a, log=lambda *x, **k: None)
        c = reg2.di_persona("dario-id")
        verifica("ripresa: la conversazione «casa» di prima va a Dario, quella dell'ospite "
                 "al suo satellite, le vuote no",
                 n == 2 and c is not None and len(c.history) == 2
                 and c.chiave == "persona:dario-id"
                 and any(x.chiave == "ospite:sat:2" for x in reg2.tutte()), n)
        a.close()


# ───────────────────────── 9. compressione per conversazione ─────────────────────────
def prova_compressione():
    from calliope.compressione import Compressore, Lavoro
    comp = Compressore.__new__(Compressore)
    comp._lock, comp._lavori, comp._ultimo = threading.Lock(), {}, None
    c1, c2 = Conversazione("persona:a"), Conversazione("persona:b")
    l1 = Lavoro(c1, "compressione", None, [], [], [], "A", None, None, "morbida")
    with comp._lock:
        comp._metti(l1)
    l1.fatto.set()
    l1.risultato = {"dati": {}}

    class B:
        conv = c2
    verifica("la compressione pronta di un'altra conversazione non si butta",
             comp.applica(B()) is None and comp._di(c1) is l1)


# ───────────────────────── 10. server dei satelliti ─────────────────────────
def prova_server():
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.server import Collegamento, ServerSatelliti

    class WS:
        def __init__(self):
            self.inviati = []

        def send(self, m):
            self.inviati.append(m)

    with tempfile.TemporaryDirectory(prefix="calliope-corsie-",
                                     ignore_cleanup_errors=True) as d:
        cfg = Config()
        cfg.memory_db = os.path.join(d, "m.db")
        srv = ServerSatelliti(cfg, ArchivioSatelliti(cfg.memory_db), log=lambda *a: None)
        srv.insieme = True
        s1, _ = srv.archivio.crea_con_token("studio")
        s2, _ = srv.archivio.crea_con_token("telefono")
        c1, c2 = Collegamento(WS(), s1, "h1"), Collegamento(WS(), s2, "h2")
        for c in (c1, c2):
            c.pronto = True
            srv._registra(c)
        attivi = [json.loads(m).get("attivo") for c in (c1, c2) for m in c.ws.inviati
                  if isinstance(m, str) and '"attivo"' in m]
        verifica("tutti insieme: ogni satellite collegato è «attivo»", attivi == [True, True],
                 attivi)
        srv._evento(c1, "audio", {"id": 1})
        verifica("eventi nella coda del satellite, non in quella comune",
                 c1.eventi.qsize() == 1 and c2.eventi.empty() and srv.eventi.empty())
        risultato = {}

        def in_corsia():
            corsie.entra(corsie.Corsia("sat:x", s2["id"]))
            risultato.update(attivo=srv.attivo, stanza=srv.stanza(),
                             presta1=srv.presta(c1), presta2=srv.presta(c2))
        t = threading.Thread(target=in_corsia)
        t.start()
        t.join(2)
        verifica("dentro una corsia `attivo` e la stanza sono del suo satellite",
                 risultato.get("attivo") is c2 and risultato.get("stanza") == "telefono",
                 risultato)
        verifica("prestito: riesce solo per il satellite della corsia, senza cambiare niente",
                 risultato.get("presta1") is False and risultato.get("presta2") is True)
        n = len(c1.ws.inviati)
        verifica("«Parla» del telefono: non toglie il posto al portatile",
                 srv.prendi(c2) and len(c1.ws.inviati) == n and c1.eventi.qsize() == 1)
        verifica("«lascia»: niente da restituire", srv.lascia(c2) is False)
        srv.archivio.close()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    for f in (prova_scelta, prova_brain, prova_sospeso, prova_scaduta_sospeso, prova_uso_doppioni, prova_varco,
              prova_condivisa, prova_smistatore, prova_ciclo, prova_voce_per_corsia, prova_pulizia_ripresa,
              prova_compressione, prova_server):
        print(f"── {f.__name__} ──")
        f()
    print(f"\n{'Tutto bene.' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
