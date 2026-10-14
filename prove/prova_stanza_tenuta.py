"""
Prova a secco della tenuta su disco del testo della stanza (14/10/2026, decisione 0029 punto 5,
progetto docs/ricerche/2026-10-13-conversazione-di-stanza.md § 3.3, § 3.10, § 4 punti 2 e 5;
calliope/stanza/tenuta.py), dietro `stanza_tenuta`.

- cosa va su disco: le righe delle persone di casa riconosciute dalla voce, adulti e minori
  (scelta di chi amministra), con stanza, tempi, «rivolta» e minore; le risposte di Calliope a
  una persona riconosciuta; le presenze;
- cosa no: le voci non riconosciute, la zona grigia, Calliope che risponde a chi non conosce,
  ciò che si dice in pausa («abbiamo ospiti»), l'audio (non c'è una colonna per lui);
- dopo un riavvio: il blocco caldo dei dati del turno resta vuoto (solo memoria), la ricerca
  trova dal disco con gli stessi permessi (chi c'era, dalle presenze sul disco; i tutori le
  parole del minore; un minore solo le sue; un ospite e la zona grigia niente);
- niente doppioni tra memoria e disco, le righe uscite dalla memoria si trovano sul disco;
- scadenza a `stanza_tenuta_giorni`, profili tolti, «dimentica» (il satellite, di ogni giorno),
  `calliope conserva --svuota` (tutto, una persona, da un altro processo), l'indice FTS5 pulito;
- conteggi in `calliope stato --turni` (sezione «Stanza»), `calliope conserva`, `dati_conservati`;
- tempi: 60 giorni di righe (~180 000) cercati con FTS5, p90 della ricerca anticipata e del
  tool sotto i 3 s (obiettivo del passo 4; misura stampata).

Contrari: spenta (nessun file, niente scritto), ospite, ignoto, zona grigia, pausa, scadenza,
permessi da disco, svuota, dimentica, riavvio. Nomi di fantasia (Carlo amministra ed è tutore di
Nicola, 14 anni; Bianca è di famiglia). ~10 s.
"""

import os
import sqlite3
import sys
import tempfile
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope import conserva as conserva_mod
from calliope.config import Config
from calliope.stanza import cerca as cerca_mod
from calliope.stanza import contesto as ctx_mod
from calliope.stanza import load_tenuta
from calliope.stanza import misure as misure_mod
from calliope.stanza import tenuta as tenuta_mod
from calliope.stanza.ascolto import Stanza
from calliope.tools import conserva as tool_conserva
from calliope.tools import stanza as tool_mod
from calliope.tools.spec import ToolContext

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio and not ok
                                                  else ""), flush=True)


class STTFinto:
    def transcribe(self, audio, **k):
        return ""


class Prof:
    def __init__(self, pid, name, nascita=None, admin=False, tutori=()):
        self.id, self.name, self.nascita, self.admin = pid, name, nascita, admin
        self.tutori = list(tutori)
        self.fascia = self.preferred_voice = self.tono = self.preferred_tone = None
        self.voce_conservata = None


class Voci:
    def __init__(self):
        self.users = {"Carlo": Prof("carlo-id", "Carlo", admin=True),
                      "Nicola": Prof("nicola-id", "Nicola", "2012-05-01",
                                     tutori=["carlo-id"]),
                      "Bianca": Prof("bianca-id", "Bianca")}

    def get(self, n):
        return self.users.get(n)

    def known_speakers(self):
        return list(self.users)


CARTELLA = tempfile.mkdtemp(prefix="calliope-tenuta-")


def cfg_base(**k) -> Config:
    c = Config()
    c.stanza, c.stanza_contesto, c.stanza_cerca = "ombra", True, True
    c.stanza_tenuta = True
    c.config_dir = CARTELLA
    c.stanza_tenuta_db = os.path.join(CARTELLA, "stanza.db")
    c.turn_log_dir = os.path.join(CARTELLA, "registro")
    c.memory_db = os.path.join(CARTELLA, "memoria.db")
    c.conversazioni_db = os.path.join(CARTELLA, "conversazioni.db")
    for a, v in k.items():
        setattr(c, a, v)
    return c


ORA = time.time()
T0 = ORA - 3 * 3600          # in cucina, tre ore fa
T1 = ORA - 3600              # in sala, un'ora fa


def riga(st, sat, testo, fine, nome=None, sicurezza="voce"):
    prof = Voci().get(nome) if nome else None
    return st.registro(sat).aggiungi(
        "riga", segmento=None, versione=1, inizio=round(fine - 2, 3), fine=round(fine, 3),
        testo=testo, chi=f"persona:{prof.id}" if prof else "ignoto", nome=nome,
        sicurezza=sicurezza if nome else "nessuna", p_min=None, rivolta="ignoto",
        minore=nome == "Nicola").seq


def stanza_nuova(cfg, sat_attivo=2):
    st = Stanza(cfg, STTFinto(), registry=Voci(), misure=misure_mod.Misure(None),
                log=lambda m: None)
    st.tenuta = load_tenuta(cfg, st.registry, log=lambda m: None)
    st._info[1] = {"nome": "satellite cucina", "stanza": "cucina", "canale": "satellite"}
    st._info[2] = {"nome": "satellite sala", "stanza": "sala", "canale": "satellite"}
    st.server = SimpleNamespace(attivo=SimpleNamespace(satellite={"id": sat_attivo}),
                                per_id=lambda s: None)
    return st


def scena(cfg):
    """Cucina (1) tre ore fa con Carlo, Bianca e Nicola; sala (2) un'ora fa con Carlo solo."""
    st = stanza_nuova(cfg)
    st._sentita("carlo-id", "Carlo", 1, T0)
    st._sentita("bianca-id", "Bianca", 1, T0 + 60)
    st._sentita("nicola-id", "Nicola", 1, T0 + 120)
    st._sentita("carlo-id", "Carlo", 1, T0 + 300)
    riga(st, 1, "Sabato andiamo in gita al lago di Borgoverde.", T0 + 10, "Carlo")
    riga(st, 1, "Porto io i panini per le gite.", T0 + 70, "Bianca")
    riga(st, 1, "Io alla gita non vengo, ho la partita.", T0 + 125, "Nicola")
    riga(st, 1, "Bella questa trasmissione sulla gita in montagna.", T0 + 200, None)
    riga(st, 1, "Allora partiamo alle nove dalla piazza per la gita.", T0 + 290, "Carlo",
         "grigia")
    st._sentita("carlo-id", "Carlo", 2, T1)              # Carlo va in sala
    riga(st, 2, "Domani chiamo l'idraulico per la caldaia.", T1 + 10, "Carlo")
    st.detto(2, "Va bene, te lo ricordo domattina.", T1 + 20, T1 + 22,
             per={"persona": "carlo-id", "sicurezza": "voce"})
    st.detto(2, "Il codice del cancello non lo so.", T1 + 30, T1 + 32,
             per={"persona": None, "sicurezza": "nessuna"})
    st.tenuta.attendi()
    return st


class Chi:
    def __init__(self, nome, livello=None, come="voce"):
        self.current_speaker = nome
        self.current_level = livello or ("amministra" if nome == "Carlo" else "familiare")
        self.identified_by = come
        self.compagnia = self.compagnia_sconosciute = False


def contesto(st, nome="Carlo", livello=None, come="voce", conserva=None):
    c = ToolContext(cfg=st.cfg, speakers=Voci(), speaker_ctx=Chi(nome, livello, come),
                    speaker=None, stanza=st)
    c.attesa = None
    c.conserva = conserva
    return c


def cerca(st, nome="Carlo", **k):
    return tool_mod._stanza_cerca(contesto(st, nome), **k)


def disco(path, sql, args=()):
    db = sqlite3.connect(path)
    try:
        return db.execute(sql, args).fetchall()
    finally:
        db.close()


# ─────────────────────────── 0. spenta ───────────────────────────
def prova_spenta():
    path = os.path.join(CARTELLA, "spenta.db")
    cfg = cfg_base(stanza_tenuta=False, stanza_tenuta_db=path)
    c = Config()
    verifica("di serie spenta, 60 giorni, file stanza.db", c.stanza_tenuta is False
             and c.stanza_tenuta_giorni == 60 and c.stanza_tenuta_db == "stanza.db")
    st = stanza_nuova(cfg)
    riga(st, 1, "Sabato andiamo in gita.", ORA - 60, "Carlo")
    verifica("contrario: spenta → nessuna tenuta, nessun file, la riga solo in memoria",
             st.tenuta is None and not os.path.exists(path) and len(st.registro(1).righe()) == 1)
    verifica("contrario: spenta → conta_file None (stato --turni non dice niente)",
             tenuta_mod.conta_file(cfg) is None)
    verifica("stanza_pausa dice «solo in memoria» con la tenuta spenta",
             "solo in memoria" in tool_mod._pausa_spec(cfg).description
             and "solo in memoria" in tool_mod._dove_tengo(st))
    st.chiudi()
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "calliope.yaml"), encoding="utf-8") as f:
        yaml_txt = f.read()
    verifica("calliope.yaml rigenerato con stanza_tenuta (false), giorni e file",
             "stanza_tenuta: false" in yaml_txt and "stanza_tenuta_giorni: 60" in yaml_txt
             and "stanza_tenuta_db: stanza.db" in yaml_txt)
    from calliope.sicurezza import file_di_dati
    verifica("il file della stanza è fra i dati personali (permessi 600 su Linux)",
             any(p.endswith("stanza.db") for p in file_di_dati(cfg_base())))


# ─────────────────────────── 1. decidi ───────────────────────────
def prova_decidi():
    v = Voci()
    d = conserva_mod.decidi
    verifica("decidi(stanza): adulto con la voce sì, minore con la voce sì (0029, ogni età)",
             bool(d(v.get("Bianca"), "stanza", "voce")) and bool(d(v.get("Nicola"), "stanza",
                                                                     "voce")))
    verifica("contrario: ospite (nessun profilo) no, zona grigia no, nessun modo no",
             not d(None, "stanza", "voce") and not d(v.get("Carlo"), "stanza", "conversazione")
             and not d(v.get("Nicola"), "stanza", None))
    verifica("le altre cose non cambiano: il testo dei turni del minore resta no",
             not d(v.get("Nicola"), "testo", "voce") and not d(v.get("Nicola"), "eventi"))


# ─────────────────────────── 2. scritture ───────────────────────────
def prova_scritture(cfg):
    st = scena(cfg)
    path = cfg.stanza_tenuta_db
    righe = disco(path, "SELECT testo, chi, nome, stanza, satellite, minore, sicurezza, "
                        "per_persona FROM righe ORDER BY inizio")
    testi = [r[0] for r in righe]
    verifica("su disco le righe di Carlo, Bianca e Nicola (minore compreso, segnato)",
             any("Borgoverde" in t for t in testi) and any("panini" in t for t in testi)
             and any(r[5] == 1 and "partita" in r[0] for r in righe), str(testi))
    verifica("con la stanza, il satellite e chi (mai una colonna per l'audio)",
             any(r[3] == "cucina" and r[4] == "satellite cucina" and r[1] == "persona:carlo-id"
                 for r in righe)
             and not any("audio" in c[1] for c in disco(path, "PRAGMA table_info(righe)")))
    verifica("contrario: la voce non riconosciuta (la TV, un ospite) mai su disco",
             not any("trasmissione" in t for t in testi))
    verifica("contrario: la zona grigia mai su disco (nel dubbio no)",
             not any("piazza" in t for t in testi))
    verifica("Calliope che risponde a Carlo sì, a una voce che non conosce no",
             any(r[1] == "calliope" and r[7] == "carlo-id" and "domattina" in r[0]
                 for r in righe) and not any("cancello" in t for t in testi))
    pres = disco(path, "SELECT persona, sat FROM presenze")
    verifica("le presenze chiuse sul disco (Carlo in cucina, uscito per la sala)",
             ("carlo-id", "1") in pres, str(pres))
    # La frase del turno e la rivolta
    seq = st.turno_testo(2, None, "Calliope, che tempo fa domani?",
                         {"chi": "persona:carlo-id", "persona": "carlo-id", "nome": "Carlo",
                          "sicurezza": "voce", "minore": False}, inizio=ORA - 30, fine=ORA - 28)
    st.segna_rivolta(2, seq, "no")
    st.tenuta.attendi()
    r = disco(path, "SELECT rivolta FROM righe WHERE testo LIKE '%che tempo fa%'")
    verifica("la frase di un turno su disco, e la rivolta rivista («no») anche lì",
             r == [("no",)], str(r))
    # Pausa per ospiti: niente, né in memoria né su disco
    prima = disco(path, "SELECT COUNT(*) FROM righe")[0][0]
    n_mem = len(st.registro(2).righe())
    st.pausa(2, "ospiti", 240)
    st.turno_testo(2, None, "Calliope, abbiamo ospiti a cena stasera.",
                   {"chi": "persona:carlo-id", "persona": "carlo-id", "nome": "Carlo",
                    "sicurezza": "voce", "minore": False})
    st.detto(2, "Va bene, buona cena.", per={"persona": "carlo-id", "sicurezza": "voce"})
    st.inizio(SimpleNamespace(satellite={"id": 2, "nome": "satellite sala"}, canale="satellite",
                              stanza="sala", ritardo=lambda: 0.0), {"id": 9, "fa_s": 0})
    st.tenuta.attendi()
    verifica("contrario: in pausa (abbiamo ospiti) niente su disco né in memoria",
             disco(path, "SELECT COUNT(*) FROM righe")[0][0] == prima
             and len(st.registro(2).righe()) == n_mem and not st._in_arrivo)
    st.riprendi(2)
    fts = disco(path, "SELECT COUNT(*) FROM righe_fts")[0][0]
    verifica("l'indice FTS5 ha una voce per riga", fts == prima, f"{fts} vs {prima}")
    return st


# ─────────────────────────── 3. memoria e disco insieme ───────────────────────────
def prova_insieme(st):
    r = cerca(st, "Carlo", parole="gita")
    testo = r.get("risultati", "")
    verifica("con memoria e disco insieme nessun doppione",
             testo.count("panini") == 1 and testo.count("Borgoverde") == 1, testo)
    # Le righe uscite dalla memoria (tenuta di 24 h, o il tetto) si trovano sul disco
    reg = st.registro(1)
    tetto = reg.max_eventi
    reg.max_eventi = 0
    reg.pota()
    reg.max_eventi = tetto
    verifica("le righe di tre ore fa non sono più in memoria", not reg.righe())
    r = cerca(st, "Carlo", parole="gita")
    testo = r.get("risultati", "")
    verifica("…e la ricerca le trova sul disco, una volta sola, nella stanza giusta",
             r.get("trovato") and testo.count("panini") == 1 and "partita" in testo
             and "In cucina:" in testo, testo)
    verifica("contrario: anche dal disco la zona grigia e la TV non ci sono",
             "piazza" not in testo and "trasmissione" not in testo, testo)
    r = cerca(st, "Bianca", parole="gita")
    verifica("Bianca dal disco: la gita sì, le parole di Nicola no",
             r.get("trovato") and "panini" in r["risultati"]
             and "partita" not in r["risultati"], str(r))


# ─────────────────────────── 4. riavvio ───────────────────────────
def prova_riavvio(cfg, st):
    # Una frase detta un minuto prima del riavvio, in sala
    riga(st, 2, "Ho messo le chiavi della cantina nel cassetto blu.", ORA - 60, "Carlo")
    st.chiudi()                                # la presenza aperta va sul disco
    st2 = stanza_nuova(cfg)
    verifica("dopo il riavvio la memoria è vuota", not st2.registro(1).righe()
             and not st2.registro(2).righe())
    b = ctx_mod.costruisci(st2, 2, cfg, ORA)
    verifica("contrario: il blocco caldo non ripesca niente dal disco (nemmeno la frase di un "
             "minuto fa)", b is None)
    verifica("contrario: il giudizio «rivolta» nemmeno", ctx_mod.righe_rivolta(st2, 2, cfg, ORA)
             == [])
    r = cerca(st2, "Carlo", parole="gita", stanza="cucina")
    testo = r.get("risultati", "")
    verifica("Carlo (tutore) dopo il riavvio trova dal disco la gita in cucina, con Bianca e "
             "Nicola", r.get("trovato") and "Borgoverde" in testo and "panini" in testo
             and "partita" in testo and "In cucina:" in testo, testo)
    r = cerca(st2, "Bianca", parole="gita")
    verifica("Bianca (non tutrice) dal disco: la gita, senza le parole di Nicola",
             r.get("trovato") and "panini" in r["risultati"]
             and "partita" not in r["risultati"], str(r))
    r = cerca(st2, "Bianca", parole="idraulico")
    verifica("contrario: Bianca non era in sala un'ora fa (presenze dal disco) → niente",
             not r.get("trovato"), str(r))
    r = cerca(st2, "Carlo", parole="idraulico")
    verifica("…Carlo c'era: l'idraulico in sala, dal disco", r.get("trovato")
             and "idraulico" in r["risultati"] and "In sala:" in r["risultati"], str(r))
    r = cerca(st2, "Nicola", parole="gita")
    verifica("un minore dal disco solo le sue righe", r.get("trovato")
             and "partita" in r["risultati"] and "Borgoverde" not in r["risultati"]
             and "panini" not in r["risultati"], str(r))
    r = cerca(st2, "Carlo", persona="Nicola")
    verifica("il tutore cerca le parole del ragazzo anche dal disco",
             r.get("trovato") and "partita" in r["risultati"], str(r))
    r = cerca(st2, "Bianca", persona="Nicola")
    verifica("contrario: un adulto non tutore che cerca il minore → no", r["ok"] is False
             and "genitore" in r["risposta_finale"])
    r = tool_mod._stanza_cerca(contesto(st2, "Ospite", "ospite", None), parole="gita")
    verifica("contrario: un ospite → no", r["ok"] is False
             and r["risposta_finale"] == tool_mod.SOLO_DI_CASA)
    r = tool_mod._stanza_cerca(contesto(st2, "Carlo", come="conversazione"), parole="gita")
    verifica("contrario: la zona grigia → no", r["ok"] is False)
    r = cerca(st2, "Carlo", parole="chiavi cantina")
    verifica("la frase di un minuto prima del riavvio si trova con la ricerca (non nel blocco)",
             r.get("trovato") and "cassetto blu" in r["risultati"], str(r))
    # La ricerca anticipata (Brain, prima della risposta) con gli stessi permessi
    a = tool_mod.anticipa(contesto(st2, "Bianca"), "Calliope, chi porta i panini per la gita?")
    verifica("la ricerca anticipata trova dal disco (Bianca: la gita, non il minore)",
             a is not None and "panini" in a.testo and "partita" not in a.testo,
             getattr(a, "testo", None))
    # Una stanza oggi scollegata, con righe sul disco: si cerca per nome
    del st2._info[1]
    r = cerca(st2, "Carlo", parole="gita", stanza="cucina")
    verifica("una stanza scollegata adesso, con righe sul disco: la si cerca per nome",
             r.get("trovato") and "In cucina:" in r["risultati"], str(r))
    st2._info[1] = {"nome": "satellite cucina", "stanza": "cucina", "canale": "satellite"}
    # Chi c'era, anche con la presenza ancora aperta al momento di un'interruzione
    st2._sentita("bianca-id", "Bianca", 2, ORA - 30)
    st2._presenze_su_disco()
    st2.tenuta.attendi()
    verifica("la presenza aperta è sul disco ogni minuto (un'interruzione non la perde)",
             ("bianca-id", "2") in disco(cfg.stanza_tenuta_db,
                                         "SELECT persona, sat FROM presenze"))
    return st2


# ─────────────────────────── 5. scadenza, profili tolti ───────────────────────────
def prova_scadenza(cfg, st):
    t = st.tenuta
    giorni = t.giorni
    vecchia = ORA - (giorni + 1) * 86400
    quasi = ORA - (giorni - 1) * 86400
    for testo, fine in (("Questa è di due mesi fa, la cena dai nonni.", vecchia),
                        ("Questa è di cinquantanove giorni fa, il pranzo al mare.", quasi)):
        t._scrivi({"sat": "1", "stanza": "cucina", "satellite": "satellite cucina",
                   "seq": 900000 + int(fine) % 1000, "segmento": None, "scambio": None,
                   "versione": 1, "inizio": fine - 2, "fine": fine, "testo": testo,
                   "chi": "persona:bianca-id", "persona": "bianca-id", "nome": "Bianca",
                   "sicurezza": "voce", "rivolta": None, "minore": 0, "per_persona": None})
    t._scrivi({"sat": "1", "stanza": "cucina", "satellite": "satellite cucina", "seq": 900999,
               "segmento": None, "scambio": None, "versione": 1, "inizio": ORA - 100,
               "fine": ORA - 98, "testo": "Sono Ugo, il profilo tolto.", "chi": "persona:ugo-id",
               "persona": "ugo-id", "nome": "Ugo", "sicurezza": "voce", "rivolta": None,
               "minore": 0, "per_persona": None})
    out = t.ruota()
    testi = [r[0] for r in disco(cfg.stanza_tenuta_db, "SELECT testo FROM righe")]
    verifica(f"scadenza: oltre {giorni} giorni via, a {giorni - 1} giorni resta",
             not any("nonni" in x for x in testi) and any("mare" in x for x in testi), str(out))
    verifica("un profilo tolto: le sue righe via alla rotazione",
             not any("Ugo" in x for x in testi) and out["senza_profilo"] >= 1, str(out))
    verifica("l'indice FTS5 segue le righe tolte",
             disco(cfg.stanza_tenuta_db, "SELECT COUNT(*) FROM righe_fts")[0][0]
             == len(testi))


# ─────────────────────────── 6. conteggi ───────────────────────────
def prova_conteggi(cfg, st):
    d = tenuta_mod.conta_file(cfg)
    verifica("conta_file: righe, persone, minori, MB (solo numeri)",
             d is not None and d["righe"] > 0 and d["persone"] == 3 and d["righe_minori"] >= 1
             and d["mb"] >= 0 and d["accesa"] is True, str(d))
    r = misure_mod.riassunto([], [])
    r["tenuta"] = d
    txt = misure_mod.testo(r)
    verifica("sezione «Stanza» di stato --turni con la tenuta su disco, senza parole né nomi",
             "Tenuta su disco" in txt and f"{d['righe']} righe" in txt
             and "Borgoverde" not in txt and "Carlo" not in txt, txt)
    c = conserva_mod.Conservazione(cfg, Voci(), log=lambda m: None)
    c.stanza = st.tenuta
    s = c.stato()
    verifica("calliope conserva: la riga della stanza su disco",
             s["stanza"]["righe"] == d["righe"]
             and "stanza su disco" in conserva_mod.testo_stato(s), conserva_mod.testo_stato(s))
    ctx = contesto(st, "Nicola", conserva=c)
    r = tool_conserva._dati_conservati(ctx, "stato")
    verifica("dati_conservati per il minore: «tengo solo quello che dici… lo possono cercare "
             "i tuoi genitori»", "genitori" in r["risposta_finale"]
             and r.get("righe_stanza", 0) >= 1, r["risposta_finale"])
    r = tool_conserva._dati_conservati(contesto(st, "Bianca", conserva=c), "stato")
    verifica("dati_conservati per un adulto: anche le frasi nella stanza",
             "nella stanza" in r["risposta_finale"], r["risposta_finale"])
    c.stanza = None
    verifica("contrario: senza tenuta il minore sente «non conservo niente»",
             "non conservo niente" in tool_conserva._dati_conservati(
                 contesto(st, "Nicola", conserva=c), "stato")["risposta_finale"])
    c.stanza = st.tenuta
    verifica("stanza_pausa con la tenuta: «la tengo per 60 giorni», non «solo in memoria»",
             "60 giorni" in tool_mod._dove_tengo(st)
             and "solo in memoria" not in tool_mod._pausa_spec(cfg).description)
    return c


# ─────────────────────────── 7. dimentica e svuota ───────────────────────────
def prova_cancella(cfg, st, c):
    path = cfg.stanza_tenuta_db
    sala = disco(path, "SELECT COUNT(*) FROM righe WHERE sat = '2'")[0][0]
    n = st.dimentica(1)
    righe = disco(path, "SELECT sat, testo FROM righe")
    verifica("«dimentica» dalla cucina: le righe della cucina via dal disco, di ogni giorno",
             not any(s == "1" for s, _ in righe) and n >= 0, str(righe))
    verifica("contrario: «dimentica» in cucina non tocca la sala",
             sum(1 for s, _ in righe if s == "2") == sala and sala > 0)
    verifica("…e le presenze della cucina via",
             not disco(path, "SELECT 1 FROM presenze WHERE sat = '1'"))
    verifica("…e l'indice FTS5 non ha più le loro parole",
             not disco(path, "SELECT rowid FROM righe_fts WHERE righe_fts MATCH 'panini'"))
    r = cerca(st, "Carlo", parole="gita")
    verifica("dopo «dimentica» la ricerca non trova più la gita", not r.get("trovato"), str(r))
    # Svuota una persona (dati_conservati / --persona): le sue righe e le risposte a lei
    riga(st, 2, "Bianca qui: compro io il latte.", ORA - 20, "Bianca")
    st.tenuta.attendi()
    r = c.svuota("carlo-id", "Carlo")
    righe = disco(path, "SELECT persona, per_persona, testo FROM righe")
    verifica("svuota di Carlo: le sue righe e le risposte di Calliope a lui via",
             r["stanza"] >= 1 and not any(p == "carlo-id" or q == "carlo-id"
                                          for p, q, _ in righe), str(righe))
    verifica("contrario: svuota di Carlo lascia le righe di Bianca",
             any("latte" in t for _, _, t in righe))
    # Da un altro processo (il terminale): il file, con la tenuta chiusa
    st.chiudi()
    c2 = conserva_mod.Conservazione(cfg, Voci(), log=lambda m: None)
    r = c2.svuota()
    verifica("calliope conserva --svuota (da terminale): il file della stanza svuotato",
             r["stanza"] >= 1 and disco(path, "SELECT COUNT(*) FROM righe")[0][0] == 0
             and disco(path, "SELECT COUNT(*) FROM righe_fts")[0][0] == 0
             and disco(path, "SELECT COUNT(*) FROM presenze")[0][0] == 0, str(r))


# ─────────────────────────── 8. tempi su 60 giorni ───────────────────────────
PAROLE = ("gita lago panini scuola compiti pizza cena nonni calcio partita idraulico caldaia "
          "vacanze mare montagna treno macchina spesa latte pane film musica libro cane gatto "
          "giardino bici medico dentista regalo compleanno").split()


def prova_tempi():
    path = os.path.join(CARTELLA, "grande.db")
    cfg = cfg_base(stanza_tenuta_db=path)
    st = stanza_nuova(cfg)
    t = st.tenuta
    n_giorno = 3000
    giorni = 60
    import random
    rnd = random.Random(7)
    nomi = [("carlo-id", "Carlo", 0), ("bianca-id", "Bianca", 0), ("nicola-id", "Nicola", 1)]
    righe, presenze = [], []
    t0 = time.perf_counter()
    for g in range(giorni):
        base = ORA - (g + 1) * 86400
        for sat in ("1", "2"):
            for pid, _, _ in nomi:
                presenze.append((pid, sat, base, base + 86400 - 1))
        for i in range(n_giorno):
            pid, nome, minore = nomi[i % 3]
            testo = " ".join(rnd.choice(PAROLE) for _ in range(8))
            fine = base + i * (86000 / n_giorno)
            righe.append(("vecchio", "1" if i % 2 else "2", "cucina" if i % 2 else "sala",
                          "sat", i + g * n_giorno, None, g, 1, fine - 2, fine, testo,
                          f"persona:{pid}", pid, nome, "voce", None, minore, None))
    with t.lock:
        t.db.executemany(
            "INSERT INTO righe(avvio, sat, stanza, satellite, seq, segmento, scambio, versione, "
            "inizio, fine, testo, chi, persona, nome, sicurezza, rivolta, minore, per_persona) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", righe)
        t.db.execute("INSERT INTO righe_fts(rowid, testo) SELECT id, testo FROM righe")
        t.db.executemany("INSERT INTO presenze(persona, sat, inizio, fine) VALUES (?, ?, ?, ?)",
                         presenze)
        t.db.commit()
    carico = time.perf_counter() - t0
    tempi_tool, tempi_ant = [], []
    domande = [("gita", ""), ("idraulico caldaia", ""), ("compleanno regalo", "ieri"),
               ("", "ieri"), ("pizza", "sera"), ("dentista", ""), ("nonni cena", ""),
               ("treno", "mattina"), ("parola_che_non_ce", ""), ("latte", "")]
    for nome in ("Carlo", "Bianca", "Nicola"):
        for parole, quando in domande:
            a = time.perf_counter()
            r = cerca(st, nome, parole=parole, quando=quando)
            tempi_tool.append((time.perf_counter() - a) * 1000)
            a = time.perf_counter()
            tool_mod.anticipa(contesto(st, nome), f"Calliope, cosa si diceva di {parole}?")
            tempi_ant.append((time.perf_counter() - a) * 1000)
    r = cerca(st, "Carlo", parole="gita")
    tempi_tool.sort()
    tempi_ant.sort()
    p50, p90 = tempi_tool[len(tempi_tool) // 2], tempi_tool[int(len(tempi_tool) * 0.9)]
    a50, a90 = tempi_ant[len(tempi_ant) // 2], tempi_ant[int(len(tempi_ant) * 0.9)]
    print(f"    misura: {len(righe)} righe in {giorni} giorni (caricate in {carico:.1f} s); "
          f"stanza_cerca p50 {p50:.0f} ms, p90 {p90:.0f} ms; ricerca anticipata p50 "
          f"{a50:.0f} ms, p90 {a90:.0f} ms", flush=True)
    verifica("60 giorni di righe: la ricerca trova", r.get("trovato") is True)
    verifica("tempi: stanza_cerca p90 sotto i 3 s (obiettivo del passo 4), anticipata pure",
             p90 < 3000 and a90 < 3000, f"{p90:.0f} ms, {a90:.0f} ms")
    st.chiudi()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        prova_spenta()
        prova_decidi()
        cfg = cfg_base()
        st = prova_scritture(cfg)
        prova_insieme(st)
        st2 = prova_riavvio(cfg, st)
        prova_scadenza(cfg, st2)
        c = prova_conteggi(cfg, st2)
        prova_cancella(cfg, st2, c)
        prova_tempi()
    finally:
        import shutil
        shutil.rmtree(CARTELLA, ignore_errors=True)
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
