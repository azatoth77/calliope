"""
La modalità studio a secco (02/11/2026, issue #376, calliope/studio/modalita.py, decisione 0035
punto 54): si apre, si chiude, scade; l'effetto 1 sulla stanza vera (solo quel satellite, la pausa
di un altro non si tocca, la ripresa); l'effetto 2 attraverso il registro dei tool (solo Studio, solo
i suoi dati, un tool fuori dallo Studio resta da ospite) e la decisione del ciclo (la voce di un altro
vince, compagnia, conoscente, minore possibile, satellite di stanza); gli endpoint col server vero
(`POST /api/vista`); il giro vero del 02/11 alle 11:46 attraverso Brain.
"""
import os, sys
sys.dont_write_bytecode = True
RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RADICE)
sys.path.insert(0, os.path.join(RADICE, "prove"))
os.chdir(RADICE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import contextlib  # noqa: E402
import datetime  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import types  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
from pathlib import Path  # noqa: E402

PT = types.ModuleType("PT")
PT.__file__ = os.path.join(RADICE, "prove", "prova_studio_tool.py")
_src = Path(PT.__file__).read_text("utf-8").split("# ═══════════════════════════ 1.")[0]
exec(compile(_src, PT.__file__, "exec"), PT.__dict__)

import prova_politica as PP  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.ciclo import Ciclo, Turno  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.schermi.hub import mittente_da  # noqa: E402
from calliope.stanza import contesto as SC  # noqa: E402
from calliope.stanza.ascolto import Stanza  # noqa: E402
from calliope.studio.modalita import MOTIVO, TOOL, Modalita  # noqa: E402
from calliope.tools import studio as TS  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402

errori = 0
LEO, ANDREA = PT.LEO, PT.ANDREA


def verifica(nome, ok, dettaglio=""):
    global errori
    if ok:
        print(f"  ok  {nome}")
    else:
        errori += 1
        print(f"ERR {nome}  {dettaglio}")


class Ora:
    def __init__(self, t=None):
        self.t = t or datetime.datetime(2026, 11, 2, 16, 0).timestamp()

    def __call__(self):
        return self.t


def cfg_mod(**k):
    c = Config()
    c.stanza = "ombra"
    c.stanza_satelliti = ["telefono", "cucina"]
    c.stanza_contesto = True
    c.turn_log_dir = tempfile.mkdtemp(prefix="calliope-modalita-")
    for a, v in k.items():
        setattr(c, a, v)
    return c


def stanza_vera(cfg):
    st = Stanza(cfg, None, registry=None, log=lambda m: None)
    for sat, nome in ((1, "telefono"), (2, "cucina")):
        st._info[sat] = {"nome": nome, "stanza": nome, "canale": "telefono"}
    return st


# ═══════════════════════════ 1. si apre, si chiude, scade ═══════════════════════════
print("— si apre, si chiude, scade; l'effetto 1 sulla stanza vera")
cfg = cfg_mod()
verifica("il valore di serie: 20 minuti", cfg.studio_modalita_inattivita_min == 20.0)
ora = Ora()
stz = stanza_vera(cfg)
md = Modalita(cfg, orologio=ora)
verifica("la stanza accesa su due satelliti", stz.accesa_qui(1) and stz.accesa_qui(2))
verifica("chiusa: nessuno stato", md.di(1, stz) is None)
for sat_ in (1, 2):
    stz.registro(sat_).aggiungi("riga", testo="Una frase della stanza", nome="Bruno",
                                sicurezza="voce", inizio=time.time() - 5, fine=time.time() - 4)
verifica("prima di aprire le righe ci sono nel blocco (il controllo di questa prova)",
         SC.costruisci(stz, 1, cfg, time.time()) is not None, stz.registro(1).righe())
md.apri(1, "l1", stz)
verifica("aperta: la stanza in pausa su quel satellite, motivo «studio»",
         stz.stato_pausa(1)["motivo"] == MOTIVO and not stz.accesa_qui(1))
verifica("contrario: l'altro satellite resta acceso", stz.accesa_qui(2) and md.di(2, stz) is None)
segni = {}
stz.schermi = types.SimpleNamespace(stanza_segno=lambda stanza, src, testo: segni.__setitem__(src, testo))
stz._segno(1)
stz._segno(2)
verifica("sugli schermi «stanza in pausa» solo per quel satellite",
         "stanza in pausa" in str(segni.get("sat:1")) and segni.get("sat:2") == "Ascolto la stanza", segni)
s1, s2 = stz.stato_per({"id": 1, "nome": "telefono"}), stz.stato_per({"id": 2, "nome": "cucina"})
verifica("al satellite lo stato dice di non mandare la stanza; all'altro sì",
         not s1.get("attiva") and s2.get("attiva"), (s1, s2))
stz.schermi = None
verifica("niente righe nel turno da lì: il blocco non c'è",
         SC.costruisci(stz, 1, cfg, time.time()) is None)
verifica("contrario: sull'altro satellite le righe ci sono",
         SC.costruisci(stz, 2, cfg, time.time()) is not None)
md.chiudi(1, stz)
verifica("uscita dalla sezione: chiusa e la stanza riprende", md.di(1, stz) is None
         and stz.accesa_qui(1))
verifica("alla ripresa le righe di prima tornano nel blocco (la pausa non le cancella)",
         SC.costruisci(stz, 1, cfg, time.time()) is not None)
md.apri(1, "l1", stz)
ora.t += 19 * 60
verifica("19 minuti dopo è viva", md.di(1, stz) is not None)
ora.t += 2 * 60
verifica("21 minuti senza attività: si chiude da sola", md.di(1, stz) is None)
verifica("…e la stanza riprende", stz.stato_pausa(1) is None)
ora.t = datetime.datetime(2026, 11, 2, 23, 55).timestamp()
md.apri(1, "l1", stz)
verifica("la pausa della stanza non passa la mezzanotte",
         stz.stato_pausa(1)["fino"] <= datetime.datetime(2026, 11, 3, 0, 0).timestamp() + 1)
ora.t = datetime.datetime(2026, 11, 3, 0, 1).timestamp()
verifica("mezzanotte: si chiude", md.di(1, stz) is None)
stz.riprendi(1)
stz.pausa(1, "ospiti")
ora.t = datetime.datetime(2026, 11, 3, 10, 0).timestamp()
md.apri(1, "l1", stz)
verifica("la pausa scelta da una persona non si tocca all'apertura",
         stz.stato_pausa(1)["motivo"] == "ospiti")
md.chiudi(1, stz)
verifica("…né alla chiusura", stz.stato_pausa(1)["motivo"] == "ospiti")
stz.riprendi(1)
c0 = cfg_mod(studio_modalita_inattivita_min=0)
verifica("0 = spenta: non si apre", not Modalita(c0).apri(1, "l1"))
verifica("in memoria: un'altra istanza (un riavvio) non ne sa niente",
         Modalita(cfg, orologio=ora).di(1, stz) is None)
verifica("i tool dello Studio: l'elenco è chiuso e quelli veri ci sono",
         {s.name for s in TS.studio_specs()} <= TOOL | {"studio_esercizio"})

# ═══════════════════════════ 2. l'effetto 2: il registro dei tool ═══════════════════════════
print("— l'effetto 2: solo i tool dello Studio, solo i suoi dati")


class HubFinto:
    def mittente(self, ctx):
        return mittente_da(ctx)


def ctx_ignoto(st, prof):
    """La voce non riconosciuta dal dispositivo personale di `prof`, con la modalità aperta."""
    c = PT.ctx_di(st, None)
    c.schermi = HubFinto()
    c.dispositivo = {"canale": "telefono", "di": prof.id}
    sc = c.speaker_ctx
    sc.from_session, sc.dispositivo_studio = False, prof.name
    sc.incerta = sc.minore_vicino = None
    return c


def materie(st):
    return sorted(r["materia"].lower() for r in st.dati.tutti("SELECT materia FROM studio_verifiche"))


st = PT.studio(PT.cfg_nuova("mod_a.db"))
reg = build_registry()
for s_ in TS.studio_specs():
    reg.register(s_)
c = ctx_ignoto(st, ANDREA)
r = json.loads(reg.call("studio", {"azione": "crea", "materia": "fisica", "data": "venerdì"}, c,
                        "ospite"))
verifica("la voce non riconosciuta dal dispositivo personale: la verifica si crea, del proprietario",
         r.get("ok") is not False and materie(st) == ["fisica"]
         and st.dati.tutti("SELECT persona FROM studio_verifiche")[0]["persona"] == ANDREA.id, r)
verifica("la regola nel registro, e chi parla torna com'era dopo la chiamata",
         "modalita_studio_voce" in c.regole and c.speaker_ctx.current_speaker is None
         and c.speaker_ctx.dispositivo_studio == ANDREA.name)
r = json.loads(reg.call("studio_verifica_sposta", {"materia": "fisica", "data": "2026-11-20"}, c,
                        "ospite"))
verifica("anche con un nome corretto dal registro (`studio_verifica_sposta`): passa dallo Studio",
         "voce non riconosciuta" not in str(r.get("motivo")), r)
r = json.loads(reg.call("ricorda", {"fatto": "mi piace la fisica"}, c, "ospite"))
verifica("contrario: un tool fuori dallo Studio resta da ospite", r.get("ok") is False
         and "voce non riconosciuta" in str(r.get("motivo")), r)
c_o = PT.ctx_di(st, None)
c_o.speaker_ctx.dispositivo_studio = None
r = json.loads(reg.call("studio", {"azione": "crea", "materia": "chimica", "data": "lunedì"}, c_o,
                        "ospite"))
verifica("contrario: senza la modalità un ospite resta un ospite", "chimica" not in materie(st)
         and r.get("ok") is False, r)
c_f = ctx_ignoto(st, ANDREA)
c_f.dispositivo = {"canale": "telefono", "di": "altro"}
r = json.loads(reg.call("studio", {"azione": "crea", "materia": "chimica", "data": "lunedì"}, c_f,
                        "ospite"))
verifica("contrario: un dispositivo non suo: niente", "chimica" not in materie(st), r)
# I suoi dati: da tutore non vede né tocca quelli del minore
vl = st.crea_verifica(ANDREA, "Storia", PT.ORA[0].date() + datetime.timedelta(days=9),
                      persona=LEO.id)
c = ctx_ignoto(st, ANDREA)
r = json.loads(reg.call("studio", {"azione": "stato", "verifica": vl}, c, "ospite"))
verifica("sui suoi dati: la verifica del minore di cui è tutore non si vede", r.get("ok") is False, r)
r = json.loads(reg.call("studio", {"azione": "crea", "materia": "latino", "data": "lunedì",
                                   "per": "Leo"}, c, "ospite"))
verifica("…e «per» un altro resta da ospite", "latino" not in materie(st), r)
c_v = PT.ctx_di(st, ANDREA)
r = json.loads(reg.call("studio", {"azione": "stato", "verifica": vl}, c_v, "familiare"))
verifica("contrario: con la voce riconosciuta il tutore la vede come prima", r.get("ok") is not False, r)
# Un proprietario minore: la regola vale e le tutele restano
c_m = ctx_ignoto(st, LEO)
r = json.loads(reg.call("studio", {"azione": "crea", "materia": "scienze", "data": "martedì"}, c_m,
                        "ospite"))
verifica("il proprietario minore: vale anche per lui, sui suoi dati", "scienze" in materie(st), r)
# La prova aperta ferma come sempre
vs = st.crea_verifica(LEO, "Arte", PT.ORA[0].date() + datetime.timedelta(days=9))
st.dati.scrivi("INSERT INTO studio_prove (verifica, persona, modalita, stato, inizio, scade) "
               "VALUES (?, ?, 'scritta', 'aperta', ?, ?)",
               (vs, LEO.id, PT.ORA[0].isoformat(),
                (PT.ORA[0] + datetime.timedelta(hours=2)).isoformat()))
r = json.loads(reg.call("studio_pagina_leggi", {"pagina": "P1", "verifica": vs}, ctx_ignoto(st, LEO),
                        "ospite"))
verifica("il blocco con una prova aperta non cambia", r.get("ok") is False
         and "testo" not in r, r)
st.close()

# ═══════════════════════════ 3. la decisione del ciclo ═══════════════════════════
print("— la decisione del ciclo: quando vale")


def ciclo_mod(proprietario="Andrea", aperta=True):
    cfg_ = cfg_mod()
    mod = Modalita(cfg_)
    if aperta:
        mod.apri(1, ANDREA.id)
    c_ = Ciclo.__new__(Ciclo)
    c_.s = types.SimpleNamespace(cfg=cfg_, registry=PT.REG, stanza=None,
                                 studio=types.SimpleNamespace(modalita=mod))
    c_.corsia = types.SimpleNamespace(satellite_id=1)
    c_.speaker_ctx = types.SimpleNamespace(
        current_speaker=None, identified_by=None, compagnia=False, compagnia_sconosciute=False,
        conoscente=None, minore_ospite=None, minore_incerto=None, minore_vicino=None, incerta=None,
        dispositivo_studio=None, from_session=False)
    c_.rec = {"voce": {"migliore": "Andrea", "punteggio": 0.375, "secondo": "Bruno",
                       "secondo_punteggio": 0.14, "margine": 0.235}}
    c_._proprietario_satellite = lambda: proprietario
    c_.rule = lambda n: None
    return c_


def vale(c_, scritto=None):
    c_.speaker_ctx.dispositivo_studio = None
    c_._modalita_voce(types.SimpleNamespace(scritto=scritto))
    return c_.speaker_ctx.dispositivo_studio


verifica("il caso vero: 0,375, il migliore è lui, secondo a 0,14 → vale lui", vale(ciclo_mod()) == "Andrea")
c_ = ciclo_mod()
c_.rec["voce"] = {"migliore": None, "punteggio": 0.0}
verifica("una voce senza nessun migliore: vale lui", vale(c_) == "Andrea")
c_ = ciclo_mod()
c_.rec["voce"] = {"migliore": "Bruno", "punteggio": 0.44}
verifica("contrario: la voce chiaramente di un altro: vince la voce", vale(c_) is None)
c_ = ciclo_mod()
c_.rec["voce"] = {"migliore": "Bruno", "punteggio": 0.20}
verifica("un altro come migliore ma lontano (0,20): non riconosciuta, vale lui", vale(c_) == "Andrea")
c_ = ciclo_mod()
c_.speaker_ctx.current_speaker = "Bruno"
verifica("contrario: riconosciuto come un altro: niente", vale(c_) is None)
for k, v in (("compagnia", True), ("compagnia_sconosciute", True), ("conoscente", {"id": 1}),
             ("minore_ospite", "Leo"), ("minore_incerto", "Leo"), ("incerta", ("A", "B"))):
    c_ = ciclo_mod()
    setattr(c_.speaker_ctx, k, v)
    verifica(f"contrario: {k}: niente", vale(c_) is None)
c_ = ciclo_mod()
c_.rec["voce"] = {"migliore": "Andrea", "punteggio": 0.40, "secondo": "Leo",
                  "secondo_punteggio": 0.37, "margine": 0.03}
verifica("contrario: il telefono di un adulto con un minore a un soffio: niente", vale(c_) is None)
verifica("contrario: un satellite di stanza (nessun proprietario): niente",
         vale(ciclo_mod(proprietario=None)) is None)
verifica("contrario: modalità chiusa: niente", vale(ciclo_mod(aperta=False)) is None)
verifica("contrario: il telefono di un altro col suo stato: niente",
         vale(ciclo_mod(proprietario="Bruno")) is None)
verifica("contrario: uno scritto: niente", vale(ciclo_mod(), scritto={"schermo_id": 1}) is None)
c_ = ciclo_mod()
c_.s.studio.modalita.orologio = lambda: time.time() + 3600
verifica("contrario: scaduta: niente", vale(c_) is None)
# Si apre dopo il turno
print("— si apre dalla chiamata di un tool")


def dopo(c_, tools, come="voce", chi="Andrea", scritto=None):
    c_.speaker_ctx.current_speaker, c_.speaker_ctx.identified_by = chi, come
    c_.brain = types.SimpleNamespace(last_tools=tools)
    c_._modalita_dopo_turno(types.SimpleNamespace(scritto=scritto))
    return c_.s.studio.modalita.di(1)


STUDIO_OK = [{"nome": "studio", "ok": False}]
verifica("la prima chiamata di un tool dello Studio, dal proprietario col suo telefono: si apre",
         dopo(ciclo_mod(aperta=False), STUDIO_OK) is not None)
verifica("contrario: un altro tool: non si apre",
         dopo(ciclo_mod(aperta=False), [{"nome": "ora_attuale", "ok": True}]) is None)
verifica("contrario: una chiamata rifiutata dalla politica: non si apre",
         dopo(ciclo_mod(aperta=False), [{"nome": "studio", "ok": False, "politica_ombra": {
             "finale": "rifiuta"}}]) is None)
verifica("contrario: un'altra voce sul suo telefono: non si apre",
         dopo(ciclo_mod(aperta=False), STUDIO_OK, chi="Bruno") is None)
verifica("contrario: un ospite: non si apre",
         dopo(ciclo_mod(aperta=False), STUDIO_OK, come=None, chi=None) is None)
verifica("contrario: un satellite di stanza: non si apre",
         dopo(ciclo_mod(proprietario=None, aperta=False), STUDIO_OK) is None)
verifica("contrario: uno scritto: non si apre",
         dopo(ciclo_mod(aperta=False), STUDIO_OK, scritto={"schermo_id": 1}) is None)
c_ = ciclo_mod(aperta=False)
c_.speaker_ctx.minore_vicino = "Leo"
verifica("contrario: con un minore possibile: non si apre", dopo(c_, STUDIO_OK) is None)
# Una riga della stanza non apre niente: la stanza non passa da qui
stz2 = stanza_vera(cfg)
md2 = Modalita(cfg)
stz2.registro(1).aggiungi("riga", testo="Calliope, apri lo studio", nome="Andrea", sicurezza="voce")
verifica("una frase che è solo una riga della stanza non apre nulla", md2.di(1, stz2) is None
         and stz2.accesa_qui(1))

# ═══════════════════════════ 4. lo schermo: POST /api/vista ═══════════════════════════
print("— lo schermo: la sezione Studio")
from calliope import minori  # noqa: E402
from calliope.schermi import ArchivioSchermi, Schermi  # noqa: E402
from calliope.schermi.server import ServerSchermi  # noqa: E402


def chiedi(port, percorso, sessione=None, token=None, corpo=None):
    h = {"Content-Type": "application/json"}
    if sessione:
        h["X-Calliope-Sessione"] = sessione
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(f"http://127.0.0.1:{port}{percorso}", headers=h, method="POST",
                                 data=json.dumps(corpo if corpo is not None else {}).encode())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {}


cfg_s = PT.cfg_nuova("mod_srv.db")
minori.prepara(cfg_s, registry=PT.REG)
st = PT.studio(cfg_s)
hub = Schermi(cfg_s, ArchivioSchermi(cfg_s.memory_db), log=lambda m: None)
hub.profilo = PT.REG.by_id
stz3 = stanza_vera(cfg_mod())
hub.servizi = types.SimpleNamespace(studio=st, stanza=stz3)
COLL = {1: types.SimpleNamespace(satellite={"id": 1, "proprietario": ANDREA.id}),
        2: types.SimpleNamespace(satellite={"id": 2, "proprietario": None})}
hub.satelliti = types.SimpleNamespace(per_id=lambda s: COLL.get(s))
srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
hub.server = srv
try:
    _, tok_a = hub.archivio.crea_con_token("telefono", proprietario=ANDREA.id,
                                           proprietario_nome="Andrea", satellite=1)
    _, tok_b = hub.archivio.crea_con_token("cucina", proprietario=ANDREA.id,
                                           proprietario_nome="Andrea", satellite=2)
    _, tok_c = hub.archivio.crea_con_token("pc", proprietario=ANDREA.id, proprietario_nome="Andrea")
    hub._rinfresca()
    ses = {k: chiedi(srv.port, "/api/accedi", token=t)[1].get("sessione")
           for k, t in (("a", tok_a), ("b", tok_b), ("c", tok_c))}
    s, _ = chiedi(srv.port, "/api/vista", ses["a"], corpo={"vista": "home"})
    verifica("la sezione Studio aperta sul suo telefono: si apre, stanza in pausa e solo lì",
             s == 200 and st.modalita.di(1, stz3) is not None
             and stz3.stato_pausa(1)["motivo"] == MOTIVO and stz3.accesa_qui(2))
    s, _ = chiedi(srv.port, "/api/vista", ses["a"], corpo={"vista": None})
    verifica("uscita dalla sezione: si chiude e la stanza riprende",
             s == 200 and st.modalita.di(1, stz3) is None and stz3.accesa_qui(1))
    chiedi(srv.port, "/api/vista", ses["b"], corpo={"vista": "home"})
    verifica("contrario: lo schermo legato a un satellite di stanza non apre nulla",
             st.modalita.di(2, stz3) is None and stz3.accesa_qui(2))
    s, _ = chiedi(srv.port, "/api/vista", ses["c"], corpo={"vista": "home"})
    verifica("contrario: uno schermo senza satellite non apre nulla", s == 200
             and st.modalita.di(1, stz3) is None)
finally:
    srv.ferma() if hasattr(srv, "ferma") else None
    st.close()

# ═══════════════════════════ 5. il giro vero del 02/11 alle 11:46 ═══════════════════════════
print("— il giro vero delle 11:46, attraverso Brain")


def riga(testo, nome="Andrea", sic="voce", chi=None):
    return {"testo": testo, "nome": nome, "sicurezza": sic, "chi": chi or nome, "t": 1.0, "seq": 1}


def blocco(righe):
    corpo = "\n".join(SC.righe_testo(righe))
    return SC.Blocco(testo=SC.provenienza.racchiudi("stanza", corpo, "conversazione della stanza"),
                     righe=len(righe), sempre=len(righe), tagliate=0, caratteri=len(corpo),
                     esterno=SC._esterno(righe), voci=SC._voci(righe))


def brain_di(st_, chi):
    reg_ = build_registry()
    for s_ in TS.studio_specs():
        reg_.register(s_)
    c__ = PT.ctx_di(st_, chi)
    for kk, vv in (("from_session", False), ("voce_sicura", getattr(chi, "name", None)),
                   ("punteggio", 0.7), ("conferma_breve", False), ("sfida", None),
                   ("sfida_superata", False), ("dispositivo_studio", None), ("incerta", None),
                   ("minore_vicino", None)):
        setattr(c__.speaker_ctx, kk, vv)
    c__.schermi = HubFinto()
    c__.dispositivo = {"canale": "telefono", "di": ANDREA.id}
    b_ = Brain(st_.cfg, reg_, c__)
    b_.backend = PP.Copione()
    return b_


def turno(b_, frase, come, righe, *risposte):
    b_.tool_ctx.speaker_ctx.identified_by = come
    b_.dispositivo_turno = {"canale": "telefono", "di": ANDREA.id}
    if righe:
        b_.stanza_turno = blocco(righe)
    b_.backend.risposte = list(risposte)
    with contextlib.redirect_stdout(io.StringIO()):
        return "".join(b_.stream_reply(frase, b_.tool_ctx.speaker_ctx.current_level))


st = PT.studio(PT.cfg_nuova("mod_giro.db"))
b = brain_di(st, ANDREA)
stz4 = stanza_vera(cfg_mod())
c4 = ciclo_mod(aperta=False)
c4.s.studio.modalita = st.modalita
c4.s.stanza = stz4
c4.brain = b
c4.speaker_ctx = b.tool_ctx.speaker_ctx
RIGHE = [riga("Calliope."), riga("Hai visto che ore sono?", nome="Bruno")]


def giro(frase, come, *risposte):
    """Un turno del giro vero: le righe della stanza solo se la stanza ascolta su quel satellite,
    e dopo il turno il ciclo che apre la modalità."""
    r_ = turno(b, frase, come, RIGHE if stz4.accesa_qui(1) else None, *risposte)
    c4._modalita_dopo_turno(types.SimpleNamespace(scritto=None))
    return r_


verifica("prima del giro la stanza ascolta", stz4.accesa_qui(1))
F1 = "Venerdì ho la verifica di fisica sulle misure delle grandezze fisiche."
r1 = giro(F1, "voce", PP.chiama("studio_proponi_data", {"materia": "fisica", "verifica": 1}),
          PP.testo("Non ho ancora la verifica di fisica."))
verifica("turno 1 (`studio_proponi_data`, verifica inventata): il turno non si chiude su «non la "
         "trovo», e la modalità si apre: stanza in pausa",
         "non la trovo" not in r1.lower() and materie(st) == [] and st.modalita.di(1, stz4) is not None
         and not stz4.accesa_qui(1), r1)
r2 = giro("Venerdì ho la verifica di fisica.", "voce",
          PP.chiama("studio", {"azione": "stato", "materia": "fisica"}),
          PP.testo("Non ho ancora alcuna verifica di fisica. Se vuoi, posso crearne una per venerdì."))
verifica("turno 2: l'offerta, niente righe nel turno", materie(st) == []
         and "stanza" not in b._turno_politica().contaminazione, r2)
CREA = {"azione": "crea", "data": "venerdì", "materia": "fisica",
        "titolo": "Verifica sulle misure delle grandezze fisiche"}
r3 = giro("Sì, grazie.", "breve", PP.chiama("studio", CREA), PP.testo("Fatto."))
verifica("turno 3, «Sì, grazie.»: con la stanza in pausa la verifica è creata",
         materie(st) == ["fisica"], (r3, b.rules_fired()))
st.modalita.chiudi(1, stz4)
verifica("uscita dalla sezione: la stanza riprende", stz4.accesa_qui(1))
st.close()
# La voce non riconosciuta nella conversazione del proprietario: la decisione del ciclo
print("— la voce non riconosciuta sta nella conversazione del proprietario")


def conv_di(c_, nome_voce=None):
    """Con che persona e come il ciclo sceglie la conversazione del turno."""
    visto = {}

    class C_:
        def turno(self, brain, nome, how, in_session, testo, rec, scritto, persona_id=None, impronta=None):
            visto.update(persona=persona_id, come=how, nome=nome)
            return True

    c_.corsia = C_()
    c_.s.cfg.debug_audio_dir = None
    c_.s.instradamento = types.SimpleNamespace(persona=lambda p: None)
    c_._chiedi_chi_parla = lambda t_: False
    c_._frasi_turno = lambda t_: None
    c_._persona_id = lambda n: {"Andrea": ANDREA.id, "Bruno": "b1"}.get(n)
    c_.brain = None
    c_._conversazione_del_turno(types.SimpleNamespace(
        speaker_name=nome_voce, continuita=False, proprietario=False, in_session=True, text="Sì, certo.",
        scritto=None, emb_job=None, audio=None))
    return visto


c_ = ciclo_mod()
vale(c_)
verifica("il ciclo: la conversazione del proprietario, come la continuità", conv_di(c_)
         == {"persona": ANDREA.id, "come": "continuita", "nome": None}, conv_di(c_))
c_ = ciclo_mod()
c_.rec["voce"] = {"migliore": "Bruno", "punteggio": 0.44}
vale(c_)
verifica("contrario: la voce chiara di un altro: l'anonima", conv_di(c_)["persona"] is None, conv_di(c_))
c_ = ciclo_mod(aperta=False)
vale(c_)
verifica("contrario: fuori dalla modalità: l'anonima", conv_di(c_)["persona"] is None, conv_di(c_))


class Visto(PP.Copione):
    """Il modello finto che tiene ciò che gli arriva."""
    def __init__(self):
        super().__init__()
        self.visti = []

    def stream(self, messages, tools):
        self.visti.append(" ".join(str(m.get("content") or "") for m in messages))
        yield from super().stream(messages, tools)


class Memoria:
    def facts(self, pid):
        return ["la password del garage è 4821"] if pid == ANDREA.id else []

    def __getattr__(self, n):
        return lambda *a, **k: []


# Il giro vero: la domanda in storia, il «Sì, certo.» a 0,375 e la verifica creata
st = PT.studio(PT.cfg_nuova("mod_giro5.db"))
b = brain_di(st, ANDREA)
b.backend = Visto()
b.tool_ctx.memory = Memoria()
sc = b.tool_ctx.speaker_ctx
DOMANDA = "Non ho ancora una verifica di fisica: vuoi che la crei per venerdì?"
r0 = turno(b, "Venerdì ho la verifica di fisica.", "voce", None, PP.testo(DOMANDA))
verifica("(il controllo di questa prova: alla voce riconosciuta i ricordi arrivano)",
         "4821" in b.backend.visti[-1], b.backend.visti[-1][-300:])
storia_prima = len(b.history)
sc.current_speaker, sc.dispositivo_studio, sc.current_level = None, "Andrea", "ospite"
r5 = turno(b, "Sì, certo.", None, None, PP.chiama("studio", {"azione": "crea", "data": "venerdì",
                                                            "materia": "fisica"}), PP.testo("Fatto."))
visto = b.backend.visti[1]
verifica("il «Sì, certo.» a 0,375: la stessa conversazione, con la domanda in storia",
         DOMANDA in visto and len(b.history) > storia_prima, visto[-400:])
verifica("…e la verifica è creata, del proprietario, per la sola chiamata",
         materie(st) == ["fisica"] and "modalita_studio_voce" in b.rules_fired()
         and st.dati.tutti("SELECT persona FROM studio_verifiche")[0]["persona"] == ANDREA.id
         and sc.current_speaker is None, (r5, b.rules_fired()))
verifica("…i ricordi del proprietario non arrivano al modello per quella frase, e i dati del turno "
         "dicono che è una voce non riconosciuta", "4821" not in visto and "voce non riconosciuta" in visto,
         visto[-400:])
r6 = turno(b, "Che tempo fa?", None, None, PP.chiama("ricorda", {"fatto": "domani piove"}), PP.testo("Va bene."))
verifica("contrario: un tool fuori dallo Studio resta da ospite", not b.last_tools[-1]["ok"], (r6, b.last_tools))
sc.current_speaker, sc.dispositivo_studio, sc.current_level = "Andrea", None, "familiare"
r7 = turno(b, "Com'è la password del garage?", "voce", None, PP.testo("Ok."))
verifica("alla voce riconosciuta, dopo, i ricordi tornano e la conversazione è la stessa",
         "4821" in b.backend.visti[-1] and DOMANDA in b.backend.visti[-1], b.backend.visti[-1][-200:])
st.close()
# I dati fissi già in storia (ricordi una volta sola, #95)
st = PT.studio(PT.cfg_nuova("mod_giro6.db"))
st.cfg.dati_stabili_in_storia = True
b = brain_di(st, ANDREA)
b.backend = Visto()
b.tool_ctx.memory = Memoria()
sc = b.tool_ctx.speaker_ctx
turno(b, "Venerdì ho la verifica di fisica.", "voce", None, PP.testo(DOMANDA))
primo = b.backend.visti[-1]
sc.current_speaker, sc.dispositivo_studio, sc.current_level = None, "Andrea", "ospite"
turno(b, "Sì, certo.", None, None, PP.testo("Ok."))
verifica("anche i ricordi già nella storia (dati fissi) escono per quella frase", "4821" in primo
         and "4821" not in b.backend.visti[-1], b.backend.visti[-1][-300:])
st.close()

print("\n" + ("TUTTO OK" if not errori else f"{errori} ERRORI"))
sys.exit(1 if errori else 0)
