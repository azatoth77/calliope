"""Prova a secco delle raccolte di «Le mie cose» e del canale «tocco» (28/10/2026, passo 2a di
docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md, issue #256 di #241; area
docs/aree/schermi-telefono.md).

1. **Le tessere** (`schermi/raccolte.tessere`) con servizi finti: i conti e lo stato in una riga
   (liste, agenda, lavori della persona, cassetto, studio), l'Ufficio solo a chi amministra (mai a
   un minore), un servizio che manca o che solleva dà la tessera «non disponibile» senza fermare
   le altre; la pagina Liste (`raccolte.pagina`) con le schede `lista`, le altre «presto», una
   raccolta non visibile 404.
2. **I tocchi** (`schermi/tocchi.prepara`): tocco sconosciuto e dati non validi 400, la voce che
   non c'è più 409, la voce tagliata dalla scheda («…») ritrovata, la voce che `lista_togli`
   dividerebbe («pane e burro») o che svuoterebbe la lista («tutto») 422, la spunta giusta →
   `lista_togli` con la voce e la lista.
3. **Il server** vero su 127.0.0.1: `/api/raccolte` (tessere e pagina) e `/api/tocco` dallo
   schermo personale; da quello di stanza 403, senza sessione 401, oltre il limite 429; il tocco
   finisce in `hub.ingresso` con il tool e gli argomenti giusti, anche senza una conversazione a
   voce.
4. **Il ciclo** (`Ciclo._tocco_dallo_schermo`) con un `ToolRegistry` vero e le `Liste` su disco:
   la voce tolta davvero, il registro dei turni con `esito` e `canale` «tocco», la descrizione
   nella storia del modello, la scheda aggiornata allo schermo del tocco, nessuna frase detta;
   i segni di chi parlava prima tornano com'erano; chi amministra con un tool che vuole la voce,
   un familiare con un tool di chi amministra e un minore con un tool dell'ufficio rifiutati, con
   l'evento «tocco» d'errore e niente nella storia; un minore spunta la lista; con il registro
   degli eventi in ombra la descrizione è un `detto_persona` col canale «tocco».

Nomi e dati di fantasia, niente rete né modelli.

    python prove/prova_raccolte.py
"""

import json
import os
import queue
import shutil
import sys
import tempfile
import threading
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from calliope import corsie  # noqa: E402
from calliope.ciclo import Ciclo, Servizi  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.cortesia import Cortesia  # noqa: E402
from calliope.liste import Liste  # noqa: E402
from calliope.schermi import ArchivioSchermi, Schermi  # noqa: E402
from calliope.schermi import raccolte, tocchi  # noqa: E402
from calliope.schermi.server import ServerSchermi  # noqa: E402
from calliope.speaker_id import SpeakerContext  # noqa: E402
from calliope.tools.builtin import FAMILY  # noqa: E402
from calliope.tools.spec import ToolContext, ToolSpec  # noqa: E402

import prova_ciclo as pc  # noqa: E402  (i finti del ciclo)
import prova_stati_buchi as sb  # noqa: E402  (Brain con il backend a copione)

TMP = Path(tempfile.mkdtemp(prefix="calliope-raccolte-"))
ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio and not ok else ""),
          flush=True)
    if not ok:
        ERRORI.append(nome)


class Profilo:
    def __init__(self, pid, nome, admin=False, nascita=None):
        self.id, self.name, self.admin, self.nascita = pid, nome, admin, nascita
        self.fascia, self.tutori, self.preferred_tone, self.preferred_voice = None, [], None, None


DARIO = Profilo("dario", "Dario", admin=True, nascita="1978-02-02")
BIANCA = Profilo("bianca", "Bianca", nascita="1981-06-06")
LIA = Profilo("lia", "Lia", nascita="2016-04-04")          # 10 anni


class Persone:
    """Il registro delle voci per SpeakerContext, il ToolContext e il ciclo."""

    def __init__(self):
        self.cfg = Config()
        self.users = {p.name: p for p in (DARIO, BIANCA, LIA)}
        self.illeggibile = False

    def get(self, nome):
        return self.users.get(nome)

    def by_id(self, pid):
        return next((p for p in self.users.values() if p.id == pid), None)


# ─────────────────────────── 1. le tessere ───────────────────────────
class Agenda:
    def __init__(self, voci):
        self.voci = voci

    def items(self, owner=None):
        return [v for v in self.voci if v["kind"] == "timer" or v.get("owner") == owner]


class Rotto:
    def recenti(self, *a, **k):
        raise RuntimeError("database chiuso")


def tessere():
    liste = Liste(str(TMP / "liste1.db"))
    liste.add("spesa", ["latte", "pane"], "Dario")
    liste.add("cose da fare", ["chiamare l'idraulico"], "Bianca")
    ora = time.time()
    agenda = Agenda([{"kind": "timer", "due": ora + 300, "created": ora - 10},
                     {"kind": "promemoria", "owner": "dario", "due": ora + 60, "created": ora - 20},
                     {"kind": "promemoria", "owner": "bianca", "due": ora + 60, "created": ora}])
    Lav = types.SimpleNamespace
    lavori = Lav(lavori=[Lav(persona="dario", stato="in_corso", creato=ora - 100, inizio=ora - 90, fine=None),
                         Lav(persona="dario", stato="fatto", creato=ora - 900, inizio=ora - 890, fine=ora - 800),
                         Lav(persona="bianca", stato="in_attesa", creato=ora, inizio=ora, fine=None)])
    cassetto = types.SimpleNamespace(elenco=lambda p: [{"arrivato": ora - 5}] if p == "dario" else [])
    numeri = types.SimpleNamespace(elenco=lambda anno=None: [{"stato": "emesso"}, {"stato": "annullato"}])
    esercizi = types.SimpleNamespace(sessione=lambda p: types.SimpleNamespace(aperta=True) if p == "lia" else None)
    hub = types.SimpleNamespace(
        servizi=types.SimpleNamespace(liste=liste, agenda=agenda, lavori=lavori, documenti=Rotto(),
                                      ufficio=types.SimpleNamespace(numeri=numeri), estensioni=None),
        tool_ctx=None, cassetto=cassetto, giochi=None, esercizi=esercizi)
    log = []
    t = {x["id"]: x for x in raccolte.tessere(hub, DARIO, log.append)}
    verifica("tessere: otto per chi amministra, nell'ordine", list(t) == [k for k, _ in raccolte.TESSERE])
    verifica("tessere: liste con il conto e i nomi", t["liste"]["conto"] == 2
             and "spesa" in t["liste"]["stato"] and t["liste"]["pagina"] is True
             and isinstance(t["liste"]["ultimo"], float), json.dumps(t["liste"]))
    verifica("tessere: agenda con il timer di casa e il promemoria suo (non quello di Bianca)",
             t["agenda"]["conto"] == 2 and "1 timer" in t["agenda"]["stato"], json.dumps(t["agenda"]))
    verifica("tessere: lavori solo della persona", t["lavori"]["conto"] == 2
             and t["lavori"]["stato"] == "1 in corso · 1 finito", json.dumps(t["lavori"]))
    verifica("tessere: cassetto", t["cassetto"]["conto"] == 1, json.dumps(t["cassetto"]))
    verifica("tessere: un servizio che solleva → «non disponibile», detto nel registro",
             t["documenti"]["conto"] is None and t["documenti"]["stato"] == "non disponibile"
             and any("documenti" in m for m in log), json.dumps(t["documenti"]))
    verifica("tessere: un servizio che manca → «non disponibile»", t["giochi"]["stato"] == "non disponibile")
    verifica("tessere: ufficio con i documenti emessi dell'anno", t["ufficio"]["conto"] == 1
             and t["ufficio"]["pagina"] is False, json.dumps(t["ufficio"]))
    verifica("tessere: le pagine non ancora fatte dicono «presto» (pagina False)",
             [k for k, v in t.items() if v["pagina"]] == ["liste"])
    tb = [x["id"] for x in raccolte.tessere(hub, BIANCA, log.append)]
    verifica("tessere: niente Ufficio a chi non amministra", "ufficio" not in tb and len(tb) == 7, str(tb))
    tl = {x["id"]: x for x in raccolte.tessere(hub, LIA, log.append)}
    verifica("tessere: niente Ufficio a un minore; lo studio aperto",
             "ufficio" not in tl and tl["studio"]["conto"] == 1, json.dumps(tl.get("studio")))
    admin_minore = Profilo("x", "Xeno", admin=True, nascita="2015-01-01")
    verifica("tessere: l'Ufficio mai a un minore, anche col segno di chi amministra",
             "ufficio" not in raccolte.visibili(admin_minore))
    # La pagina Liste
    p = raccolte.pagina(hub, BIANCA, "liste")
    sc = p.get("schede") or []
    verifica("pagina: le liste di casa con le schede «lista»",
             [c.get("tipo") for c in sc] == ["lista", "lista"]
             and {c.get("chiave") for c in sc} == {"lista:spesa", "lista:cose da fare"}
             and any(v["testo"] == "latte" for c in sc for v in c["voci"]), json.dumps(p)[:300])
    p = raccolte.pagina(hub, DARIO, "agenda")
    verifica("pagina: una raccolta senza pagina dice «presto»", p.get("schede") == [] and "presto" in p.get("nota", ""))
    p = raccolte.pagina(hub, BIANCA, "ufficio")
    verifica("pagina: l'Ufficio a chi non amministra 404", p.get("_stato") == 404)
    vuoto = types.SimpleNamespace(servizi=None, tool_ctx=None)
    verifica("tessere: senza servizi tutte «non disponibile»",
             all(x["stato"] == "non disponibile" for x in raccolte.tessere(vuoto, DARIO, lambda m: None)))
    liste.db.close()


# ─────────────────────────── 2. i tocchi ───────────────────────────
def prepara_tocchi():
    liste = Liste(str(TMP / "liste2.db"))
    lunga = "x" * 90
    liste.add("spesa", ["latte", "pane e burro", "tutto", lunga], "Dario")
    fonti = types.SimpleNamespace(liste=liste)
    verifica("tocchi: tocco sconosciuto 400", tocchi.prepara({"tocco": "cancella_tutto"}, fonti).get("_stato") == 400)
    verifica("tocchi: dati non validi 400", tocchi.prepara([1, 2], fonti).get("_stato") == 400
             and tocchi.prepara({"tocco": "spunta_lista", "lista": "spesa"}, fonti).get("_stato") == 400
             and tocchi.prepara({"tocco": "spunta_lista", "lista": "spesa", "voce": 3}, fonti).get("_stato") == 400)
    verifica("tocchi: senza liste 503", tocchi.prepara({"tocco": "spunta_lista", "lista": "spesa", "voce": "latte"},
                                                       types.SimpleNamespace()).get("_stato") == 503)
    r = tocchi.prepara({"tocco": "spunta_lista", "lista": "spesa", "voce": "uova"}, fonti)
    verifica("tocchi: la voce che non c'è più 409", r.get("_stato") == 409 and "uova" in r.get("errore", ""))
    r = tocchi.prepara({"tocco": "spunta_lista", "lista": "spesa", "voce": "pane e burro"}, fonti)
    verifica("tocchi: una voce che lista_togli dividerebbe 422", r.get("_stato") == 422, json.dumps(r))
    r = tocchi.prepara({"tocco": "spunta_lista", "lista": "spesa", "voce": "tutto"}, fonti)
    verifica("tocchi: una voce che svuoterebbe la lista 422", r.get("_stato") == 422, json.dumps(r))
    r = tocchi.prepara({"tocco": "spunta_lista", "lista": "la lista della spesa", "voce": " latte "}, fonti)
    verifica("tocchi: la spunta → lista_togli con la voce e la lista",
             r.get("tool") == "lista_togli" and r.get("argomenti") == {"cose": "latte", "lista": "spesa"}
             and r.get("descrizione") == "(Ho tolto «latte» dalla lista della spesa toccando lo schermo.)",
             json.dumps(r, ensure_ascii=False))
    from calliope.schermi import schede
    tagliata = next(v["testo"] for v in schede.lista("spesa", liste.read("spesa")[1])["voci"] if v["testo"].endswith("…"))
    r = tocchi.prepara({"tocco": "spunta_lista", "lista": "spesa", "voce": tagliata}, fonti)
    verifica("tocchi: la voce tagliata dalla scheda («…») è quella intera",
             r.get("argomenti", {}).get("cose") == lunga, json.dumps(r)[:200])
    liste.db.close()


# ─────────────────────────── 3. il server ───────────────────────────
def chiedi(port, percorso, sessione=None, token=None, corpo=None):
    h = {"Content-Type": "application/json"}
    if sessione:
        h["X-Calliope-Sessione"] = sessione
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(f"http://127.0.0.1:{port}{percorso}", headers=h, method="POST",
                                 data=json.dumps(corpo if corpo is not None else {}).encode("utf-8"))
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def server():
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "memoria.db")
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    reg = Persone()
    hub.profilo = reg.by_id
    liste = Liste(str(TMP / "liste3.db"))
    liste.add("spesa", ["latte", "uova"], "Dario")
    hub.tool_ctx = ToolContext(cfg=cfg, speakers=reg, speaker_ctx=None, speaker=None, liste=liste)
    srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
    hub.server = srv
    try:
        arch = hub.archivio
        _, t_bianca = arch.crea_con_token("telefono", proprietario="bianca", proprietario_nome="Bianca")
        _, t_cucina = arch.crea_con_token("cucina")
        hub._rinfresca()
        port = srv.port
        sess = chiedi(port, "/api/accedi", token=t_bianca)[1].get("sessione")
        sess_c = chiedi(port, "/api/accedi", token=t_cucina)[1].get("sessione")
        st, d = chiedi(port, "/api/raccolte", sess, corpo={})
        ids = [x.get("id") for x in d.get("tessere") or []]
        verifica("server: /api/raccolte dà le tessere del proprietario (senza Ufficio)",
                 st == 200 and ids and "ufficio" not in ids and "liste" in ids, f"{st} {d}")
        t = next((x for x in d.get("tessere") or [] if x["id"] == "liste"), {})
        verifica("server: la tessera Liste con il conto dal servizio", t.get("conto") == 1, json.dumps(t))
        st, d = chiedi(port, "/api/raccolte", sess, corpo={"raccolta": "liste"})
        verifica("server: /api/raccolte {raccolta: liste} dà le schede",
                 st == 200 and [c.get("chiave") for c in d.get("schede") or []] == ["lista:spesa"], f"{st} {d}")
        st, d = chiedi(port, "/api/raccolte", sess, corpo={"raccolta": "ufficio"})
        verifica("server: l'Ufficio a chi non amministra 404", st == 404, f"{st} {d}")
        st, _ = chiedi(port, "/api/raccolte", sess_c, corpo={})
        verifica("server: da uno schermo di stanza 403", st == 403, str(st))
        st, _ = chiedi(port, "/api/raccolte", None, corpo={})
        verifica("server: senza sessione 401", st == 401, str(st))
        st, _ = chiedi(port, "/api/tocco", sess_c, corpo={"tocco": "spunta_lista", "lista": "spesa", "voce": "latte"})
        verifica("server: il tocco da uno schermo di stanza 403", st == 403 and hub.ingresso.vuoto(), str(st))
        st, d = chiedi(port, "/api/tocco", sess, corpo={"tocco": "spunta_lista", "lista": "spesa", "voce": "pane"})
        verifica("server: il tocco su una voce che non c'è 409, niente al ciclo", st == 409 and hub.ingresso.vuoto(),
                 f"{st} {d}")
        verifica("server: nessuna conversazione a voce aperta (lo scritto sarebbe rifiutato)",
                 not hub.scrittura_consentita(next(s for s in hub.abbinati() if s.get("proprietario")))[0])
        st, d = chiedi(port, "/api/tocco", sess, corpo={"tocco": "spunta_lista", "lista": "spesa", "voce": "latte"})
        item = hub.ingresso.prendi() or {}
        verifica("server: il tocco anche senza conversazione → {ok, in_coda} e l'elemento nell'ingresso",
                 st == 200 and d == {"ok": True, "in_coda": True} and item.get("tipo") == "tocco"
                 and item.get("tool") == "lista_togli" and item.get("argomenti") == {"cose": "latte", "lista": "spesa"}
                 and item.get("persona") == "bianca" and item.get("tocco") == "spunta_lista"
                 and item.get("schermo") == "telefono di bianca" and isinstance(item.get("schermo_id"), int)
                 and "latte" in item.get("descrizione", ""), f"{st} {d} {item}")
        verifica("server: il tocco non tocca la lista (la cambia il ciclo)", liste.read("spesa")[1] == ["latte", "uova"])
        codici = [chiedi(port, "/api/raccolte", sess, corpo={})[0] for _ in range(30)]
        verifica("server: oltre 30 letture al minuto 429", 429 in codici and codici[0] == 200, str(codici[-3:]))
        hub.tool_ctx = None
        st, _ = chiedi(port, "/api/tocco", sess, corpo={"tocco": "spunta_lista", "lista": "spesa", "voce": "uova"})
        verifica("server: senza il contesto dei tool 503", st == 503, str(st))
        hub.tool_ctx = ToolContext(cfg=cfg, speakers=reg, speaker_ctx=None, speaker=None, liste=liste)
        codici_t = [chiedi(port, "/api/tocco", sess, corpo={"tocco": "spunta_lista", "lista": "spesa",
                                                          "voce": "nulla"})[0] for _ in range(30)]
        verifica("server: oltre 30 tocchi al minuto 429", codici_t[-1] == 429 and 409 in codici_t,
                 str(codici_t[-3:]))
    finally:
        srv.ferma()
        liste.db.close()


# ─────────────────────────── 4. il ciclo ───────────────────────────
class HubFinto:
    """Gli schermi per il ciclo: l'ingresso vero, le schede inviate a uno schermo, gli eventi
    «tocco»; `scrittura_consentita` dice «nessuna conversazione» e conta le chiamate (il tocco
    non deve chiederla: decisione 1 del 28/10)."""

    def __init__(self):
        from calliope.schermi.moduli import Ingresso
        self.inviate, self.a_tutti, self.eventi, self.consentita = [], [], [], 0
        self.ingresso = Ingresso()

    def invia(self, scheda, mittente):                  # agli schermi di casa: mai per un tocco
        self.a_tutti.append((scheda, mittente))
        return {"schermi": ["salotto"], "motivo": None}

    def invia_a(self, sid, scheda):
        self.inviate.append((sid, scheda))
        return True

    def evento_a(self, sid, tipo, dati):
        self.eventi.append((sid, tipo, dati))
        return 1

    def scrittura_consentita(self, schermo):
        self.consentita += 1
        return False, "nessuna_conversazione"

    def schermo(self, sid):
        return {"id": sid, "proprietario": "bianca"}


class Archivio:
    """L'archivio delle conversazioni di Brain: la conversazione corrente salvata su «disco»."""

    def __init__(self):
        self.salvate = []

    def salva_corrente(self, conv):
        self.salvate.append([dict(m) for m in conv.history])

    def archivia(self, *a, **k):
        pass

    def chiudi(self, *a, **k):
        pass


def prepara_ciclo(modo="spento"):
    b = sb.brain([])
    reg = Persone()
    b.cfg = reg.cfg
    b.cfg.eventi = modo
    b.cfg.speaker_id_enabled = False
    b.cfg.debug_audio_dir = None
    b.cfg.uscita_controllo = False
    b.archivio_conv = Archivio()
    sc = SpeakerContext(reg)
    liste = Liste(str(TMP / f"liste-ciclo-{modo}.db"))
    liste.add("spesa", ["latte", "uova", "pane"], "Bianca")
    b.tool_ctx = ToolContext(cfg=b.cfg, speakers=reg, speaker_ctx=sc, speaker=None, liste=liste)
    # Un tool dell'ufficio per i familiari: a un minore lo nega il preset (minori.permesso)
    b.tools.register(ToolSpec(name="anagrafica_cerca", description="", parameters={},
                              func=lambda ctx: {"ok": True}, risk="lettura", levels=FAMILY))
    turni, voce = [], pc.Voce()
    instr = types.SimpleNamespace(dopo_turno=lambda x: x, inizio_voce=lambda: None,
                                  persona=lambda *a: None, origine=lambda: {},
                                  annuncia_verso=lambda *a, **k: None,
                                  risposta_scritta=lambda *a: True,
                                  inizio_scritto=lambda *a: "satellite")
    registri = None
    if modo != "spento":
        from calliope.eventi.registro import Disco, Registri
        registri = Registri(Disco.file(str(TMP / f"conv-{modo}.db")), log=lambda m: None)
    srv = Servizi(b.cfg, registry=reg, stt=pc.Whisper(), instradamento=instr, cortesia=Cortesia(),
                  turns=types.SimpleNamespace(write=lambda r: turni.append(dict(r))),
                  attiva_minori=lambda: False, enroll_pending=False, eventi=registri)
    srv.tools = b.tools
    srv.barge_in, srv.wake = True, object()
    annunci = types.SimpleNamespace(agenda=queue.Queue(), documenti=queue.Queue(),
                                    installazioni=None, lavori=None, estensioni=None)
    hub = HubFinto()
    c = Ciclo(srv, corsie.Corsia("locale"), pc.Ascolto(), voce, sc, b, b.tool_ctx, annunci,
              hub.ingresso, threading.Event())
    c.s.schermi = b.tool_ctx.schermi = hub
    return b, c, sc, liste, turni, voce, hub, registri


def tocca(c, item):
    """Un giro del ciclo con il tocco nell'ingresso (come lo mette /api/tocco), passando da
    `_prendi_scritto` e senza conversazione a voce; poi il turno nel registro."""
    assert c.s.schermi.ingresso.metti(dict(item))
    c.giro()
    if c.rec is not None:
        c._scrivi_turno(c.rec)
        c.rec = None


def voce_tocco(persona, voce="latte", sid=7):
    p = tocchi.prepara({"tocco": "spunta_lista", "lista": "spesa", "voce": voce},
                       types.SimpleNamespace(liste=CORRENTE["liste"]))
    return {"tipo": "tocco", "tool": p["tool"], "argomenti": p["argomenti"], "descrizione": p["descrizione"],
            "tocco": "spunta_lista", "persona": persona, "schermo": "telefono", "stanza": None,
            "schermo_id": sid, "arrivato": time.time(), "pagina": {"lista": "spesa", "voce": voce}}


CORRENTE = {}


def ruoli(storia):
    return [m.get("role") for m in storia]


def due_user(storia) -> bool:
    r = ruoli(storia)
    return any(a == b == "user" for a, b in zip(r, r[1:]))


def ciclo():
    b, c, sc, liste, turni, voce, hub, _ = prepara_ciclo()
    CORRENTE["liste"] = liste
    # La voce di prima: Dario a voce, con i segni della frase (compagnia, conferma breve)
    sc.current_speaker, sc.identified_by, sc.from_session = "Dario", "voce", False
    sc.compagnia, sc.conferma_breve = True, True
    tocca(c, voce_tocco("bianca"))
    r = turni[-1] if turni else {}
    verifica("ciclo: il tocco passa da _prendi_scritto senza chiedere la conversazione a voce",
             hub.consentita == 0 and r.get("esito") == "tocco", f"{hub.consentita} {r.get('esito')}")
    verifica("ciclo: la voce è tolta davvero dalla lista", liste.read("spesa")[1] == ["uova", "pane"],
             str(liste.read("spesa")))
    verifica("ciclo: il registro dei turni con esito e canale «tocco», chi tocca e il tool",
             r.get("esito") == "tocco" and r.get("canale") == "tocco" and r.get("livello") == "familiare"
             and (r.get("voce") or {}).get("nome") == "Bianca" and (r.get("voce") or {}).get("modo") == "schermo"
             and (r.get("tool") or [{}])[0].get("nome") == "lista_togli" and r["tool"][0].get("ok") is True
             and r["tool"][0].get("azione") is True and "latte" in (r.get("testo") or ""), json.dumps(r, ensure_ascii=False)[:400])
    coda = b.history[-4:]
    verifica("ciclo: nella storia il turno con la sua chiamata (frase, lista_togli, esito, conferma di Calliope)",
             ruoli(coda) == ["user", "assistant", "tool", "assistant"]
             and coda[3]["content"] == "Ho tolto latte dalla lista della spesa." and not coda[3].get("tool_calls")
             and coda[0]["content"] == "(Ho tolto «latte» dalla lista della spesa toccando lo schermo.)"
             and coda[1]["tool_calls"][0]["name"] == "lista_togli"
             and coda[1]["tool_calls"][0]["arguments"] == {"cose": "latte", "lista": "spesa"}
             and json.loads(coda[2]["content"]).get("ok") is True, json.dumps(coda, ensure_ascii=False)[:400])
    verifica("ciclo: la conversazione salvata con il tocco (resta dopo un riavvio)",
             b.archivio_conv.salvate and b.archivio_conv.salvate[-1][-4:] == [dict(m) for m in coda])
    verifica("ciclo: dopo il tocco l'ultimo messaggio della storia è di Calliope", b.history[-1]["role"] == "assistant")
    verifica("ciclo: il tocco vale come ultimo turno (la conversazione non scade alla frase dopo)",
             time.monotonic() - (getattr(b, "last_turn_at", None) or 0) < 5)
    verifica("ciclo: nessuna frase detta (chi tocca può essere al supermercato)", voce.detto == [], str(voce.detto))
    inv = [s for sid, s in hub.inviate if s.get("tipo") == "lista" and sid == 7]
    verifica("ciclo: la lista aggiornata solo allo schermo del tocco (anche con le schede automatiche "
             "spente; mai alla TV di casa)",
             inv and [v["testo"] for v in inv[-1]["voci"]] == ["uova", "pane"] and not hub.a_tutti,
             str(hub.inviate[-1:])[:300])
    verifica("ciclo: l'evento «tocco» riuscito allo schermo, con ciò che la pagina aveva toccato",
             hub.eventi and hub.eventi[-1][:2] == (7, "tocco") and hub.eventi[-1][2].get("ok") is True
             and hub.eventi[-1][2].get("pagina") == {"lista": "spesa", "voce": "latte"})
    verifica("ciclo: i segni di chi parlava prima tornano com'erano",
             sc.current_speaker == "Dario" and sc.identified_by == "voce" and sc.compagnia is True
             and sc.conferma_breve is True, f"{sc.current_speaker} {sc.identified_by} {sc.compagnia}")
    verifica("ciclo: il contesto dei tool torna com'era (niente frase del tocco)",
             getattr(b.tool_ctx, "user_text", "") == "" and getattr(b.tool_ctx, "politica", None) is None)
    # Due tocchi di fila: mai due messaggi della persona uno dopo l'altro
    tocca(c, voce_tocco("bianca", "uova"))
    verifica("ciclo: due tocchi di fila, mai due messaggi della persona uno dopo l'altro",
             not due_user(b.history) and ruoli(b.history[-8:]) == ["user", "assistant", "tool", "assistant"] * 2,
             str(ruoli(b.history)))
    liste.add("spesa", ["latte", "uova"], "Bianca")
    # Una conversazione ferma da troppo: si chiude prima del tocco, come prima di una risposta
    b.cfg.storia_inattiva_s = 60
    b.last_turn_at = time.monotonic() - 3600
    vecchia = len(b.history)
    tocca(c, voce_tocco("bianca", "latte"))
    verifica("ciclo: la conversazione scaduta si chiude prima; il tocco apre la nuova",
             vecchia >= 8 and ruoli(b.history) == ["user", "assistant", "tool", "assistant"], str(ruoli(b.history)))
    b.cfg.storia_inattiva_s = 0

    def rifiuto(nome, item, attesa):
        n_storia, n_ev = len(b.history), len(hub.eventi)
        prima = liste.read("spesa")[1]
        tocca(c, item)
        r = turni[-1]
        ev = hub.eventi[-1][2] if len(hub.eventi) > n_ev else {}
        verifica(nome, r.get("esito") == "rifiutato" and r.get("canale") == "tocco"
                 and attesa(r, ev) and ev.get("ok") is False and ev.get("errore")
                 and len(b.history) == n_storia and liste.read("spesa")[1] == prima and voce.detto == [],
                 json.dumps({"rec": r, "ev": ev}, ensure_ascii=False)[:500])

    base = {"tipo": "tocco", "descrizione": "(prova)", "tocco": "spunta_lista", "schermo": "telefono",
            "schermo_id": 7, "arrivato": time.time()}
    rifiuto("ciclo: chi amministra, con un tool che vuole la sua voce: rifiutato perché serve la voce",
            {**base, "persona": "dario", "tool": "registra_utente", "argomenti": {"nome": "Ugo"}},
            lambda r, ev: r.get("livello") == "familiare" and r["tool"][0].get("ok") is False
            and "scritto_serve_voce" in (r.get("regole") or []) and "voce" in ev.get("errore", ""))
    rifiuto("ciclo: un familiare con un tool di chi amministra, rifiutato (permesso_livello)",
            {**base, "persona": "bianca", "tool": "registra_utente", "argomenti": {"nome": "Ugo"}},
            lambda r, ev: "permesso_livello" in (r.get("regole") or []) and r["tool"][0].get("ok") is False)
    rifiuto("ciclo: un minore con un tool dell'ufficio, rifiutato dal suo preset (minore_ufficio)",
            {**base, "persona": "lia", "tool": "anagrafica_cerca", "argomenti": {}},
            lambda r, ev: (r.get("voce") or {}).get("nome") == "Lia"
            and "minore_ufficio" in (r.get("regole") or []) and r["tool"][0].get("ok") is False)
    # Fuori dagli orari decisi dai tutori: il tocco di un minore non cambia niente
    import calliope.ciclo as ciclo_mod
    vero = ciclo_mod.minori.fuori_orario
    ciclo_mod.minori.fuori_orario = lambda prof, adesso=None: ("21:00-07:00" if getattr(prof, "id", "") == "lia"
                                                               else vero(prof, adesso))
    try:
        rifiuto("ciclo: un minore fuori dagli orari dei tutori, rifiutato con la frase degli orari",
                voce_tocco("lia", "pane"),
                lambda r, ev: r.get("motivo") == "fuori_orario" and "minore_fuori_orario" in (r.get("regole") or [])
                and "7:00" in ev.get("errore", ""))
        tocca(c, voce_tocco("bianca", "pane"))
        verifica("ciclo: gli orari valgono solo per il minore (un adulto spunta)",
                 turni[-1].get("esito") == "tocco" and "pane" not in liste.read("spesa")[1])
    finally:
        ciclo_mod.minori.fuori_orario = vero
    liste.add("spesa", ["pane"], "Bianca")
    tocca(c, {**base, "persona": "ugo", "tool": "lista_togli", "argomenti": {"cose": "uova"}})
    r = turni[-1]
    verifica("ciclo: lo schermo di una persona che non c'è più, niente a nome di nessuno",
             r.get("esito") == "rifiutato" and "uova" in liste.read("spesa")[1]
             and hub.eventi[-1][2].get("ok") is False, json.dumps(r)[:300])
    # Un'eccezione dentro il tocco: la pagina riceve comunque l'esito d'errore
    rotto = c.s.tools.call
    c.s.tools.call = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("guasto"))
    try:
        n = len(hub.eventi)
        tocca(c, voce_tocco("bianca", "uova"))
    finally:
        c.s.tools.call = rotto
    verifica("ciclo: un'eccezione nel tocco manda comunque l'esito d'errore alla pagina",
             len(hub.eventi) > n and hub.eventi[-1][2].get("ok") is False and hub.eventi[-1][2].get("errore")
             and turni[-1].get("esito") == "rifiutato" and "tocco_errore" in turni[-1].get("regole", [])
             and sc.current_speaker == "Dario", json.dumps(turni[-1])[:300])
    tocca(c, voce_tocco("lia", "uova"))
    verifica("ciclo: un minore spunta la lista (i tool delle liste sono per la famiglia)",
             turni[-1].get("esito") == "tocco" and "uova" not in liste.read("spesa")[1],
             json.dumps(turni[-1], ensure_ascii=False)[:300])
    liste.db.close()


def ciclo_eventi():
    b, c, sc, liste, turni, voce, hub, registri = prepara_ciclo("ombra")
    CORRENTE["liste"] = liste
    sc.current_speaker, sc.identified_by = "Dario", "voce"
    tocca(c, voce_tocco("bianca"))
    r = turni[-1] if turni else {}
    eventi = list(registri.della_corsia(b.conv.chiave).eventi())
    dp = [e.dati for e in eventi if e.tipo == "detto_persona"]
    verifica("eventi: il tocco è un detto_persona col canale «tocco», la descrizione e come «schermo»",
             r.get("esito") == "tocco" and dp and dp[-1].get("canale") == "tocco" and dp[-1].get("come") == "schermo"
             and "latte" in dp[-1].get("testo", ""), json.dumps(dp, ensure_ascii=False)[:300])
    chiamate = [e.dati for e in eventi if e.tipo == "chiamata_tool"]
    verifica("eventi: anche la chiamata di lista_togli negli eventi",
             any(x.get("nome") == "lista_togli" for x in chiamate), json.dumps(chiamate, ensure_ascii=False)[:300])
    from calliope.eventi import proiezioni
    vista = proiezioni.turni(eventi)
    msgs = [{k: v for k, v in m.items() if k in ("role", "content")}
            | ({"tool": [x["name"] for x in m["tool_calls"]]} if m.get("tool_calls") else {})
            for m in proiezioni.messaggi(vista)]
    storia = [{k: v for k, v in m.items() if k in ("role", "content")}
              | ({"tool": [x["name"] for x in m["tool_calls"]]} if m.get("tool_calls") else {})
              for m in b.history]
    verifica("eventi: la proiezione dà la stessa storia di Brain, conferma di Calliope compresa",
             [m["role"] for m in msgs] == [m["role"] for m in storia] == ["user", "assistant", "tool", "assistant"]
             and msgs[0] == storia[0] and msgs[1].get("tool") == storia[1].get("tool") == ["lista_togli"]
             and msgs[3] == storia[3] == {"role": "assistant", "content": "Ho tolto latte dalla lista della spesa."},
             json.dumps([msgs, storia], ensure_ascii=False)[:600])
    muti = [e.dati for e in eventi if e.tipo == "detto_calliope" and e.dati.get("atto") == "tocco_esito"]
    verifica("eventi: la conferma è un detto_calliope col canale «muta», mai detto a voce",
             muti and muti[-1].get("canale") == "muta" and voce.detto == [], json.dumps(muti, ensure_ascii=False)[:300])
    ombra = r.get("eventi_ombra") or {}
    from calliope.eventi.misura import DICHIARATI
    verifica("eventi: l'ombra non vede differenze nel turno del tocco (solo «canale_scritto», dichiarato: "
             "la conferma è muta)", not set(ombra.get("differenze") or {}) - DICHIARATI,
             json.dumps(ombra, ensure_ascii=False)[:300])
    from calliope.eventi.tipi import CANALI_PERSONA
    verifica("eventi: «tocco» tra i canali della persona", "tocco" in CANALI_PERSONA)
    registri.disco.db.close()
    liste.db.close()


def main():
    try:
        print("— 1. le tessere")
        tessere()
        print("— 2. i tocchi")
        prepara_tocchi()
        print("— 3. il server")
        server()
        print("— 4. il ciclo")
        ciclo()
        ciclo_eventi()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(ERRORI)} errori" if ERRORI else "\ntutto ok")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
