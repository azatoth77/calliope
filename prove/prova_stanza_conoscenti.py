"""
Prova a secco dei conoscenti (14/10/2026, decisione 0030; calliope/stanza/conoscenti.py,
calliope/tools/conoscenti.py), dietro `stanza_conoscenti`. Impronte finte (vettori quasi
ortogonali, una per voce), Whisper finto, schermi finti.

- la regola `conoscente_nome` (vocativi, saluti, presentazioni, terza persona) con i contrari;
- i gruppi delle voci sconosciute in memoria, la deduzione dal vocativo seguito dalla risposta e
  dalla presentazione, la proposta solo sullo schermo personale di chi amministra (mai di stanza,
  mai di un altro familiare, mai a voce), niente su disco prima del sì;
- il sì (nome proposto o diverso, cognome, nota), il conoscente riconosciuto nelle righe dopo con
  il nome e la nota, su disco con la tenuta, cercato come la famiglia (chi c'era) e per nome e
  cognome; livello ospite (nessun tool di chi amministra, niente fuori dalla stanza);
- omonimie: un familiare con lo stesso nome (proposto e segnalato, mai fuso), un conoscente con
  lo stesso nome e un'altra voce («un altro Marco, non Marco Rossi?»), due profili distinti, il
  doppione esatto rifiutato, «dimentica Marco» che chiede quale;
- il no (non ripropone la stessa voce), indizi discordi, nome in terza persona, il vocativo a cui
  risponde il familiare con quel nome, voce di bambino con lo stimatore (mai proposta) e senza
  (l'avviso), la scadenza a 180 giorni, «dimentica», `calliope conserva --svuota` da un altro
  processo e dal processo, il file senza copia;
- promozione a familiare e ritorno: solo chi amministra a voce, con la domanda e il sì; minore con
  nascita e tutori; contrari: familiare, ospite, scritto, zona grigia, chi amministra o un minore
  da declassare, nome già in famiglia; le righe su disco seguono il cambio;
- misure senza nomi né parole e la riga di `calliope stato --turni`; configurazione;
- (14/10 sera, rifiniture) il conoscente che parla a Calliope: chi parla «Marco Rossi
  (conoscente)» nei dati del turno e nella riga della stanza, livello ospite, nel registro dei
  turni solo `conoscente: true`; la famiglia vince sempre (voce netta, zona grigia, a parità,
  frase breve, omonima) e senza stanza niente cambia; le presenze dei conoscenti (memoria, disco,
  blocco della stanza «… (conoscente)»), che passano con lui alla promozione (e cerca dove
  c'era già) e al ritorno, e spariscono quando lo si dimentica.

Nomi di fantasia: Carlo amministra ed è tutore di Nicola (14 anni), Bianca è di famiglia; gli
ospiti sono Marco, un altro Marco, una seconda Bianca. ~3 s.
"""

import json
import os
import sqlite3
import sys
import tempfile
import time
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope import conserva as conserva_mod
from calliope import politica as pol
from calliope.config import Config
from calliope.stanza import cerca as cerca_mod
from calliope.stanza import conoscenti as con_mod
from calliope.stanza import contesto as ctx_mod
from calliope.stanza import load_conoscenti_stanza, load_tenuta
from calliope.stanza import misure as misure_mod
from calliope.stanza.ascolto import Segmento, Stanza
from calliope.tools import conoscenti as tool_mod
from calliope.tools import stanza as tool_stanza
from calliope.tools.spec import ToolContext

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio and not ok
                                                  else ""), flush=True)


DIM = 24


def voce(i: int, rumore: float = 0.0, seme: int = 0) -> np.ndarray:
    v = np.zeros(DIM, dtype=np.float32)
    v[i] = 1.0
    if rumore:
        v += np.random.default_rng(seme).normal(0, rumore, DIM).astype(np.float32)
    return (v / np.linalg.norm(v)).astype(np.float32)


CARLO, BIANCA, NICOLA = 0, 1, 2
MARCO, MARCO2, BIANCA2, BAMBINO, DISCORDE, RIFIUTATO, TERZA, PAOLO = 5, 6, 7, 8, 9, 10, 11, 12


class Prof:
    def __init__(self, pid, name, v, nascita=None, admin=False, tutori=()):
        self.id, self.name, self.nascita, self.admin = pid, name, nascita, admin
        self.tutori = list(tutori)
        self.fascia = self.preferred_voice = self.tono = self.preferred_tone = None
        self.voce_conservata = None
        self.voiceprint = voce(v)
        self.model = "finto"


class Voci:
    """Il registro delle voci finto: embed dal marcatore nell'audio, classifica col prodotto."""

    def __init__(self):
        self.users = {"Carlo": Prof("carlo-id", "Carlo", CARLO, admin=True),
                      "Nicola": Prof("nicola-id", "Nicola", NICOLA, "2012-05-01",
                                     tutori=["carlo-id"]),
                      "Bianca": Prof("bianca-id", "Bianca", BIANCA)}
        self.embedder = SimpleNamespace(model_name="finto")
        self.salvato = 0

    def get(self, n):
        return self.users.get(n)

    def by_id(self, pid):
        return next((u for u in self.users.values() if u.id == pid), None)

    def find(self, n):
        from calliope.speaker_id import name_key
        k = name_key(n)
        for u in self.users:
            uk = name_key(u)
            if uk == k or (k and (len(uk.split()) == 1 or len(k.split()) == 1)
                           and uk.split()[0] == k.split()[0]):
                return u
        return None

    def save(self):
        self.salvato += 1

    def known_speakers(self):
        return list(self.users)

    def embed(self, audio, sr):
        i = int(round(float(audio[1]) * 32768 / 100))
        return voce(i, 0.03, seme=int(round(float(audio[0]) * 32768 / 100)))

    def classifica(self, emb):
        return sorted(((n, float(np.dot(emb, p.voiceprint))) for n, p in self.users.items()
                       if p.voiceprint is not None), key=lambda x: -x[1])


class STTFinto:
    def __init__(self):
        self.testi = {}

    def transcribe(self, audio, **k):
        return self.testi.get(int(round(float(audio[0]) * 32768 / 100)), "")


class HubFinto:
    def __init__(self, collegati=(1, 2, 3)):
        self.schermi = [{"id": 1, "proprietario": "carlo-id"}, {"id": 2, "proprietario": None},
                        {"id": 3, "proprietario": "bianca-id"}]
        self.collegati = set(collegati)
        self.mandate = []

    def abbinati(self):
        return list(self.schermi)

    def collegato(self, sid):
        return sid in self.collegati

    def invia_a(self, sid, scheda):
        self.mandate.append((sid, scheda))
        return sid in self.collegati

    def stanza_segno(self, *a):
        pass


CARTELLA = tempfile.mkdtemp(prefix="calliope-conoscenti-")


def cfg_base(**k) -> Config:
    c = Config()
    c.stanza, c.stanza_contesto, c.stanza_cerca = "ombra", True, True
    c.stanza_tenuta = True
    c.stanza_conoscenti = True
    c.config_dir = CARTELLA
    c.stanza_tenuta_db = os.path.join(CARTELLA, "stanza.db")
    c.conoscenti_file = os.path.join(CARTELLA, "conoscenti.json")
    c.turn_log_dir = os.path.join(CARTELLA, "registro")
    c.speaker_id_threshold, c.speaker_id_margine = 0.48, 0.08
    c.speaker_min_voice_s = 1.0
    for a, v in k.items():
        setattr(c, a, v)
    return c


class Scena:
    """Una stanza con la tenuta e i conoscenti; `di(voce, testo)` è un segmento trascritto."""

    def __init__(self, cfg, voci=None, eta=None, hub=None):
        self.cfg = cfg
        self.voci = voci or Voci()
        self.stt = STTFinto()
        self.mis = misure_mod.Misure(None)
        self.st = Stanza(cfg, self.stt, registry=self.voci, misure=self.mis, log=lambda m: None)
        self.st.tenuta = load_tenuta(cfg, self.voci, log=lambda m: None)
        self.st.conoscenti = load_conoscenti_stanza(cfg, self.st, self.voci, self.mis,
                                                    log=lambda m: None)
        self.con = self.st.conoscenti
        self.con.eta = eta
        self.hub = hub or HubFinto()
        self.con.schermi = self.hub
        self.st._info[1] = {"nome": "satellite cucina", "stanza": "cucina", "canale": "satellite"}
        self.st._info[2] = {"nome": "satellite sala", "stanza": "sala", "canale": "satellite"}
        self.st.server = SimpleNamespace(attivo=SimpleNamespace(satellite={"id": 1}),
                                         per_id=lambda s: None)
        self.n = 0
        self.t = time.time() - 600

    def di(self, v: int, testo: str, sat=1, voce_s=3.0, salta=4.0):
        """La voce `v` dice `testo` nella stanza `sat` (un segmento trascritto)."""
        self.n += 1
        self.stt.testi[self.n] = testo
        a = np.zeros(16000, dtype=np.int16)
        a[0], a[1] = self.n * 100, v * 100
        s = Segmento(sat, "satellite", "satellite", self.n, time.monotonic())
        s.pezzi, s.byte = [a.tobytes()], a.nbytes
        s.voce_s = voce_s
        self.t += salta
        s.inizio_epoch, s.fine_epoch = self.t, self.t + 2.0
        s.chiuso = s.fine = time.monotonic()
        s.scambio = 1
        self.st._trascrivi(s)
        return self.st.registro(sat).righe()[-1]

    def chiudi(self):
        if self.st.tenuta is not None:
            self.st.tenuta.attendi()
        self.st.chiudi()


def eventi(mis, evento=None):
    return [r for r in mis.memoria if r.get("tipo") == "conoscenti"
            and (evento is None or r.get("evento") == evento)]


def scheda_a(hub, sid):
    return [s for i, s in hub.mandate if i == sid]


def marco_presentato(sc: Scena, v=MARCO, nome="Marco"):
    """Bianca saluta, la voce nuova risponde; Carlo la chiama, risponde; si presenta."""
    sc.di(BIANCA, f"Ciao {nome}! Che bello vederti.")
    sc.di(v, "Ciao a tutti, scusate il ritardo, c'era traffico.")
    sc.di(CARLO, f"{nome}, tu che dici della gita di sabato?")
    sc.di(v, "Per me va benissimo, porto io le bibite per tutti.")
    sc.di(v, f"Comunque piacere, sono {nome}, il collega di Carlo.")


# ─────────────────────────── 1. la regola ───────────────────────────
def prova_regola():
    n = con_mod.nomi_in
    casi = [("Ciao Marco!", [], ["Marco"], []), ("Marco, tu che dici?", [], ["Marco"], []),
            ("Sei d'accordo, Marco?", [], ["Marco"], []),
            ("Ciao, sono Marco.", ["Marco"], [], []), ("Mi chiamo Gaia.", ["Gaia"], [], []),
            ("Piacere, Marco", [], ["Marco"], []),
            ("Senti, Luca, passami il sale", [], ["Luca"], []),
            ("Ho visto Marco ieri sera", [], [], ["Marco"]),
            ("Ci sono Marco e Luca", [], [], ["Marco", "Luca"])]
    for testo, p, v, t in casi:
        r = n(testo, {"Calliope"})
        verifica(f"regola: «{testo}»", (r.presentazioni, r.vocativi, r.terza) == (p, v, t),
                 str(r))
    for testo in ("Allora, che facciamo?", "Buongiorno a tutti", "Calliope, che ore sono?",
                  "Grazie, ciao!", "Senti, dimmi una cosa", "Mamma, dove sei?",
                  "Domani, se piove, restiamo a casa.", "Sabato andiamo al mare"):
        r = n(testo, {"Calliope"})
        verifica(f"regola contrario: «{testo}» non ha nomi",
                 not (r.presentazioni or r.vocativi or r.terza), str(r))
    r = n("Ciao cucina, accendi la luce", {"Calliope", "cucina"})
    verifica("regola contrario: un nome escluso (stanza) non è una persona",
             not (r.vocativi or r.presentazioni))


# ─────────────────────────── 2. deduzione e proposta ───────────────────────────
def prova_proposta():
    cfg = cfg_base()
    sc = Scena(cfg)
    con, hub = sc.con, sc.hub
    verifica("spento di serie, 180 giorni, soglia 3, 6 s, file conoscenti.json",
             Config().stanza_conoscenti is False and Config().conoscenti_scadenza_giorni == 180
             and Config().conoscenti_soglia == 3 and Config().conoscenti_min_voce_s == 6.0
             and Config().conoscenti_file == "conoscenti.json")
    r = sc.di(BIANCA, "Ciao Marco! Che bello vederti.")
    verifica("la famiglia resta la famiglia (Bianca riconosciuta)",
             r["chi"] == "persona:bianca-id" and r["sicurezza"] == "voce")
    r = sc.di(MARCO, "Ciao a tutti, scusate il ritardo.")
    verifica("la voce sconosciuta è «ignoto» con il suo gruppo (in memoria)",
             r["chi"] == "ignoto" and r.get("gruppo") is not None)
    g = con.gruppo(r["gruppo"])
    verifica("un indizio: il vocativo seguito dalla risposta della voce",
             [(i.nome, i.forma) for i in g.indizi] == [("Marco", "vocativo")])
    verifica("niente proposta con un indizio solo", not hub.mandate)
    sc.di(CARLO, "Marco, tu che dici della gita di sabato?")
    sc.di(MARCO, "Per me va benissimo, porto io le bibite.")
    verifica("due vocativi (2 punti): ancora niente", not hub.mandate
             and con.punteggi(g)[0][:2] == ("Marco", 2))
    verifica("niente su disco prima del sì (né file né righe della voce)",
             not os.path.exists(cfg.conoscenti_file))
    sc.di(MARCO, "Comunque piacere, sono Marco, il collega di Carlo.")
    a1, a2, a3 = scheda_a(hub, 1), scheda_a(hub, 2), scheda_a(hub, 3)
    verifica("presentazione (2 punti): proposta sullo schermo personale di chi amministra",
             len(a1) == 1 and a1[0]["tipo"] == "conoscente" and a1[0]["visibilita"] == "personale")
    verifica("contrario: mai sullo schermo di stanza né su quello di un altro familiare",
             not a2 and not a3)
    p = a1[0]
    verifica("la domanda, il nome e un pezzo breve di trascrizione",
             "che chiamate Marco" in p["domanda"] and p["nome"] == "Marco"
             and 0 < len(p["estratto"]) <= 3 and all(len(x) < 200 for x in p["estratto"]))
    verifica("senza stimatore dell'età la proposta lo dice",
             any("età" in a for a in p["avvisi"]))
    verifica("la scheda non va nella cronologia su disco",
             "conoscente" in __import__("calliope.schermi.cronologia",
                                        fromlist=["x"]).NON_SALVATE)
    verifica("niente su disco anche dopo la proposta", not os.path.exists(cfg.conoscenti_file))
    verifica("misure: gruppo nuovo, proposta, mandata (senza nomi)",
             eventi(sc.mis, "gruppo_nuovo") and eventi(sc.mis, "proposta")
             and eventi(sc.mis, "mandata")
             and "Marco" not in json.dumps(eventi(sc.mis), ensure_ascii=False))
    out = con.risposta(p["proposta"], "si", "carlo-id", "Marco", "Rossi", "collega di Carlo")
    verifica("sì con cognome e nota: salvato", out.get("ok") and "Marco Rossi" in out["frase"],
             str(out))
    d = json.loads(open(cfg.conoscenti_file, encoding="utf-8").read())
    verifica("su disco: un profilo con nome, cognome, nota e impronta; nessuna copia .bak",
             len(d["conoscenti"]) == 1 and d["conoscenti"][0]["cognome"] == "Rossi"
             and d["conoscenti"][0]["impronta"]
             and not os.path.exists(cfg.conoscenti_file + ".bak"))
    verifica("la scheda aggiornata (chiusa) allo schermo di chi amministra",
             scheda_a(hub, 1)[-1]["aperta"] is False)
    verifica("contrario: la stessa proposta non si risponde due volte",
             not con.risposta(p["proposta"], "si", "carlo-id").get("ok"))
    r = sc.di(MARCO, "Sabato porto anche la torta di mele.")
    verifica("le volte dopo: riconosciuto, col nome e la nota nella riga",
             r["chi"].startswith("conoscente:") and r["nome"] == "Marco Rossi"
             and r["nota"] == "collega di Carlo" and r["sicurezza"] == "voce")
    verifica("l'etichetta del blocco caldo distingue il conoscente",
             ctx_mod.etichetta(r) == "Marco Rossi (collega di Carlo), conoscente")
    sc.st.tenuta.attendi()
    db = sqlite3.connect(cfg.stanza_tenuta_db)
    righe = db.execute("SELECT persona, nome, nota FROM righe WHERE chi LIKE 'conoscente:%'"
                       ).fetchall()
    ignote = db.execute("SELECT COUNT(*) FROM righe WHERE chi = 'ignoto'").fetchone()[0]
    db.close()
    verifica("su disco la riga del conoscente (con la nota); mai le righe di prima, da ignoto",
             len(righe) == 1 and righe[0][1] == "Marco Rossi"
             and righe[0][2] == "collega di Carlo" and ignote == 0, str(righe))
    # La ricerca: come la famiglia, chi c'era; per nome e cognome
    st = sc.st
    st._sentita("carlo-id", "Carlo", 1, sc.t - 30)
    ctx = contesto(sc, "Carlo")
    r = tool_stanza._stanza_cerca(ctx, parole="torta", persona="Marco Rossi")
    verifica("ricerca: «cosa ha detto Marco Rossi della torta?» trova la sua riga",
             r.get("trovato") and "Marco Rossi" in r["risultati"] and "torta" in r["risultati"],
             str(r))
    chi = cerca_mod.Chi(pid="zoe-id", nome="Zoe", sat=None)
    es = cerca_mod.cerca(st, cfg, chi, "torta", adesso=sc.t + 3 * 86400)
    verifica("contrario: un adulto che non c'era (nessuna presenza) non la trova",
             es.esito == "niente")
    sc.chiudi()
    return cfg


def contesto(sc, nome="Carlo", livello=None, come="voce", breve_ok=False, turno=1):
    voci = sc.voci if isinstance(sc, Scena) else sc
    sc_ = SimpleNamespace(current_speaker=nome, identified_by=come, conferma_breve=breve_ok,
                          compagnia=False, compagnia_sconosciute=False)
    prof = voci.get(nome) if nome else None
    lv = livello or ("amministra" if prof is not None and prof.admin else
                     "familiare" if prof is not None else "ospite")
    sc_.current_level = sc_.profile_level = lv
    st = sc.st if isinstance(sc, Scena) else None
    c = ToolContext(cfg=sc.cfg, speakers=voci, speaker_ctx=sc_, speaker=None, stanza=st)
    c.attesa = None
    c.turno = turno
    return c


# ─────────────────────────── 3. omonimie ───────────────────────────
def prova_omonimie():
    cfg = cfg_base(conoscenti_file=os.path.join(CARTELLA, "omonimi.json"),
                   stanza_tenuta_db=os.path.join(CARTELLA, "omonimi.db"))
    sc = Scena(cfg)
    con, hub = sc.con, sc.hub
    marco_presentato(sc)
    p1 = scheda_a(hub, 1)[-1]
    con.risposta(p1["proposta"], "si", "carlo-id", "Marco", "Rossi", "collega di Carlo")
    # Un altro Marco, un'altra voce
    marco_presentato(sc, MARCO2)
    p2 = scheda_a(hub, 1)[-1]
    verifica("omonimo conoscente: proposto, e la proposta dice «un altro Marco, non Marco Rossi?»",
             p2["proposta"] != p1["proposta"] and any(
                 "un altro Marco, non Marco Rossi?" in a for a in p2["avvisi"]), str(p2))
    gem = con.risposta(p2["proposta"], "si", "carlo-id", "Marco", "Rossi", "collega di Carlo")
    verifica("contrario: lo stesso nome, cognome e nota di un altro conoscente → chiede di "
             "distinguerli", not gem.get("ok") and "distinguerli" in gem.get("errore", ""))
    out = con.risposta(p2["proposta"], "si", "carlo-id", "Marco", "", "papà di Luca")
    verifica("con una nota diversa: un profilo nuovo, mai fuso", out.get("ok")
             and len(con.elenco()) == 2 and len({c.id for c in con.elenco()}) == 2)
    r1 = sc.di(MARCO, "Io prendo il treno delle otto.")
    r2 = sc.di(MARCO2, "Io invece vengo in macchina.")
    verifica("le due voci restano due persone, distinte nelle righe",
             r1["chi"] != r2["chi"] and ctx_mod.etichetta(r1).startswith("Marco Rossi")
             and ctx_mod.etichetta(r2) == "Marco (papà di Luca), conoscente")
    # Un nome di famiglia: proposto come omonimo, segnalato
    marco_presentato(sc, BIANCA2, "Bianca")
    p3 = scheda_a(hub, 1)[-1]
    verifica("omonimo di famiglia: proposto (non escluso) e segnalato",
             p3["nome"] == "Bianca" and any("In famiglia c'è già Bianca" in a
                                            for a in p3["avvisi"]), str(p3))
    # Il vocativo a cui risponde la Bianca di casa non è un indizio per nessuno
    n0 = sum(len(g.indizi) for g in con._gruppi.values())
    sc.di(CARLO, "Bianca, mi passi il pane?")
    sc.di(BIANCA, "Eccolo, tieni.")
    verifica("contrario: «Bianca, …» seguito dalla Bianca di casa non conta",
             sum(len(g.indizi) for g in con._gruppi.values()) == n0)
    # «Dimentica Marco» con due Marco: chiede quale
    ctx = contesto(sc, "Carlo")
    r = tool_mod._conoscenti(ctx, "dimentica", "Marco")
    verifica("«dimentica Marco» con due Marco: chiede quale, con cognome e nota",
             not r["ok"] and "Quale?" in r["risposta_finale"]
             and "collega di Carlo" in r["risposta_finale"]
             and "papà di Luca" in r["risposta_finale"], str(r))
    r = tool_mod._conoscenti(ctx, "dimentica", "Marco papà di Luca")
    verifica("con la nota: la domanda per quello giusto",
             not r["ok"] and "papà di Luca" in r["risposta_finale"] and "in_sospeso" in r)
    ctx.turno = 2
    r = tool_mod._conoscenti(ctx, "dimentica", "Marco papà di Luca")
    verifica("il sì: dimenticato solo lui", r["ok"] and len(con.elenco()) == 1
             and con.elenco()[0].cognome == "Rossi")
    sc.chiudi()


# ─────────────────────────── 4. contrari della deduzione ───────────────────────────
def prova_contrari():
    cfg = cfg_base(conoscenti_file=os.path.join(CARTELLA, "contrari.json"),
                   stanza_tenuta_db=os.path.join(CARTELLA, "contrari.db"))
    sc = Scena(cfg)
    con, hub = sc.con, sc.hub
    # Terza persona: «ho visto Paolo» e poi la voce risponde → niente
    for _ in range(4):
        sc.di(BIANCA, "Ieri ho visto Paolo al mercato, era stanchissimo.")
        sc.di(TERZA, "Davvero? Chissà come mai.")
    g = con.gruppo(sc.st.registro(1).righe()[-1]["gruppo"])
    verifica("contrario: un nome detto in terza persona non è un indizio",
             not g.indizi and not hub.mandate)
    # Di sé in terza persona: un contrario
    sc.di(BIANCA, "Ciao Paolo!")
    sc.di(PAOLO, "Ciao, ma Paolo dice sempre così.")
    gp = con.gruppo(sc.st.registro(1).righe()[-1]["gruppo"])
    verifica("contrario: il nome detto dalla voce stessa in terza persona toglie un punto",
             con.punteggi(gp)[0][:2] == ("Paolo", 0), str(con.punteggi(gp)))
    # Indizi discordi
    sc.di(BIANCA, "Ciao Luca!")
    sc.di(DISCORDE, "Ciao, come va?")
    sc.di(CARLO, "Matteo, vieni a vedere?")
    sc.di(DISCORDE, "Arrivo subito.")
    sc.di(BIANCA, "Matteo, ti piace?")
    sc.di(DISCORDE, "Moltissimo, grazie.")
    sc.di(DISCORDE, "Piacere, sono Luca.")
    gd = con.gruppo(sc.st.registro(1).righe()[-1]["gruppo"])
    verifica("contrario: indizi discordi (Luca 3, Matteo 2) → niente proposta",
             not hub.mandate and eventi(sc.mis, "discordi"), str(con.punteggi(gd)))
    # Poca voce: niente
    for _ in range(2):
        sc.di(BIANCA, "Ciao Sara!")
        sc.di(13, "Ciao!", voce_s=1.2)
    sc.di(13, "Sono Sara.", voce_s=1.2)
    verifica("contrario: poca voce per un'impronta buona (3,6 s) → niente proposta",
             not hub.mandate)
    # Il no
    marco_presentato(sc, RIFIUTATO, "Giorgio")
    p = scheda_a(hub, 1)[-1]
    out = con.risposta(p["proposta"], "no", "carlo-id")
    verifica("no: niente su disco", out.get("ok") and not os.path.exists(cfg.conoscenti_file))
    n = len(hub.mandate)
    marco_presentato(sc, RIFIUTATO, "Giorgio")
    verifica("dopo il no la stessa voce non si ripropone", len(hub.mandate) == n)
    gid = sc.st.registro(1).righe()[-1]["gruppo"]
    con._togli_gruppo(gid)                           # il gruppo esce dalla memoria
    marco_presentato(sc, RIFIUTATO, "Giorgio")
    verifica("…nemmeno in un gruppo nuovo (l'impronta rifiutata, in memoria)",
             len(hub.mandate) == n and eventi(sc.mis, "rifiuto"))
    sc.chiudi()
    # Il bambino: con lo stimatore mai
    cfg2 = cfg_base(conoscenti_file=os.path.join(CARTELLA, "bambino.json"),
                    stanza_tenuta_db=os.path.join(CARTELLA, "bambino.db"))
    sc2 = Scena(cfg2, eta=lambda emb: "bambino" if np.argmax(emb) == BAMBINO else "adulto")
    marco_presentato(sc2, BAMBINO, "Tommaso")
    verifica("minore sconosciuto: con lo stimatore dell'età mai proposto",
             not sc2.hub.mandate and eventi(sc2.mis, "minore"))
    marco_presentato(sc2, MARCO, "Marco")
    pa = scheda_a(sc2.hub, 1)
    verifica("un adulto con lo stimatore: proposto, senza l'avviso dell'età",
             pa and not any("età" in a for a in pa[-1]["avvisi"]))
    sc2.chiudi()
    # Nessuno schermo di chi amministra collegato: si riprova dopo
    cfg3 = cfg_base(conoscenti_file=os.path.join(CARTELLA, "attesa.json"),
                    stanza_tenuta_db=os.path.join(CARTELLA, "attesa.db"))
    sc3 = Scena(cfg3, hub=HubFinto(collegati=(2, 3)))
    marco_presentato(sc3)
    verifica("senza lo schermo di chi amministra la proposta aspetta (mai altrove)",
             not [m for m in sc3.hub.mandate if m[0] != 1] and sc3.con.proposte_aperte()
             and not sc3.con.proposte_aperte()[0].mandata)
    sc3.hub.collegati.add(1)
    sc3.con.ogni_tanto()
    verifica("…e arriva quando si collega", sc3.con.proposte_aperte()[0].mandata)
    sc3.chiudi()


# ─────────────────────────── 5. permessi, scadenza, cancellazione ───────────────────────────
def prova_permessi_e_scadenza():
    cfg = cfg_base(conoscenti_file=os.path.join(CARTELLA, "scadenza.json"),
                   stanza_tenuta_db=os.path.join(CARTELLA, "scadenza.db"))
    sc = Scena(cfg)
    con, hub = sc.con, sc.hub
    marco_presentato(sc)
    con.risposta(scheda_a(hub, 1)[-1]["proposta"], "si", "carlo-id", "Marco", "Rossi", "")
    c = con.elenco()[0]
    verifica("permessi: un conoscente è della categoria «conoscente» (livello ospite)",
             conserva_mod.categoria(c) == "conoscente")
    verifica("permessi: per la conservazione solo la stanza con la voce, mai turni, voce, "
             "eventi, conversazioni",
             conserva_mod.decidi(c, "stanza", "voce").ok
             and not conserva_mod.decidi(c, "stanza", "grigia").ok
             and not any(conserva_mod.decidi(c, k, "voce").ok
                         for k in ("testo", "voce", "eventi", "conversazioni")))
    verifica("permessi: non è nel registro delle voci della famiglia (nessun comando lo vede)",
             all(p.id != c.id for p in sc.voci.users.values()))
    sc.di(MARCO, "Domani porto il vino.")
    sc.st.tenuta.attendi()
    # La scadenza
    con.ruota(time.time() + 181 * 86400)
    sc.st.tenuta.attendi()
    db = sqlite3.connect(cfg.stanza_tenuta_db)
    n = db.execute("SELECT COUNT(*) FROM righe WHERE persona LIKE 'conoscente:%'").fetchone()[0]
    db.close()
    verifica("scadenza: dopo 180 giorni senza sentirlo via profilo, impronta e righe su disco",
             not con.elenco() and n == 0 and eventi(sc.mis, "scaduto"))
    r = sc.di(MARCO, "Sono ancora qui.")
    verifica("…e la sua voce torna sconosciuta", r["chi"] == "ignoto")
    verifica("…anche le sue righe in memoria tornano senza nome",
             all(not str(x.get("chi")).startswith("conoscente:")
                 for x in sc.st.registro(1).righe()))
    # Dimentica a voce: contrari
    marco_presentato(sc, MARCO2, "Luigi")
    con.risposta(scheda_a(hub, 1)[-1]["proposta"], "si", "carlo-id")
    for chi, come, nome in (("familiare", "voce", "Bianca"), ("ospite", "voce", None),
                            ("amministra", "schermo", "Carlo"), ("amministra", "conversazione",
                                                                 "Carlo")):
        ctx = contesto(sc, nome, chi, come)
        r = tool_mod._conoscenti(ctx, "dimentica", "Luigi")
        verifica(f"contrario: «dimentica Luigi» da {nome or 'un ospite'} ({come}) non va",
                 not r["ok"] and len(con.elenco()) == 1, str(r))
    spec = {s.name: s for s in tool_mod.conoscenti_specs()}
    verifica("i tool sono solo di chi amministra",
             set(spec["conoscenti"].levels) == {"amministra"}
             and set(spec["conoscente_livello"].levels) == {"amministra"})
    verifica("conoscente_livello è pericoloso, chiesto e con la sfida; conoscenti distruttivo "
             "per «dimentica»",
             pol.CLASSI["conoscente_livello"].classe == "pericoloso"
             and pol.CLASSI["conoscente_livello"].sfida
             and pol.CLASSI["conoscente_livello"].chiesta
             and "dimentica" in pol.CLASSI["conoscenti"].distruttiva
             and pol.CLASSI["conoscenti"].sola_lettura == ("azione", frozenset({"elenco"})))
    ctx = contesto(sc, "Carlo")
    r = tool_mod._conoscenti(ctx, "elenco")
    verifica("elenco a chi amministra", r["ok"] and "Luigi" in r["risposta_finale"])
    # conserva --svuota da un altro processo
    n = con_mod.svuota_file(cfg)
    con._sincro = 0.0
    verifica("calliope conserva --svuota (altro processo): il file via, Calliope se ne accorge",
             n == 1 and not os.path.exists(cfg.conoscenti_file) and not con.elenco())
    # e dal processo
    marco_presentato(sc, PAOLO, "Paolo")
    con.risposta(scheda_a(hub, 1)[-1]["proposta"], "si", "carlo-id")
    cons = conserva_mod.Conservazione(cfg, sc.voci, log=lambda m: None)
    cons.stanza, cons.conoscenti = sc.st.tenuta, con
    out = cons.svuota()
    verifica("dati_conservati svuota (dal processo): conoscenti cancellati, gruppi e proposte "
             "in memoria via", out.get("conoscenti") == 1 and not con.elenco()
             and not con._gruppi and not os.path.exists(cfg.conoscenti_file), str(out))
    sc.chiudi()


# ─────────────────────────── 6. promozione e ritorno ───────────────────────────
def prova_livello():
    cfg = cfg_base(conoscenti_file=os.path.join(CARTELLA, "livello.json"),
                   stanza_tenuta_db=os.path.join(CARTELLA, "livello.db"))
    sc = Scena(cfg)
    con, hub, voci = sc.con, sc.hub, sc.voci
    marco_presentato(sc)
    con.risposta(scheda_a(hub, 1)[-1]["proposta"], "si", "carlo-id", "Marco", "Rossi",
                 "collega di Carlo")
    c = con.elenco()[0]
    sc.di(MARCO, "Porto io il vino stasera.")
    sc.st.tenuta.attendi()
    for chi, come, nome, breve in (("familiare", "voce", "Bianca", False),
                                   ("ospite", "voce", None, False),
                                   ("amministra", "schermo", "Carlo", False),
                                   ("amministra", "conversazione", "Carlo", False),
                                   ("amministra", "breve", "Carlo", False)):
        r = tool_mod._conoscente_livello(contesto(sc, nome, chi, come, breve), "promuovi",
                                         "Marco Rossi")
        verifica(f"contrario: promozione chiesta da {nome or 'un ospite'} ({come}) non va",
                 not r["ok"] and "Marco Rossi" not in voci.users, str(r))
    ctx = contesto(sc, "Carlo", turno=5)
    r = tool_mod._conoscente_livello(ctx, "promuovi", "Marco Rossi")
    verifica("promozione: prima la domanda", not r["ok"] and "in_sospeso" in r
             and "Marco Rossi" not in voci.users)
    ctx.turno = 6
    r = tool_mod._conoscente_livello(ctx, "promuovi", "Marco Rossi")
    prof = voci.users.get("Marco Rossi")
    verifica("al sì: familiare con lo stesso id e la stessa impronta, fuori dai conoscenti, e "
             "la proposta di rifare la voce", r["ok"] and prof is not None and prof.id == c.id
             and float(np.dot(prof.voiceprint, c.impronta)) > 0.999 and not prof.admin
             and not con.elenco() and "registra di nuovo la voce" in r["risposta_finale"],
             str(r))
    sc.st.tenuta.attendi()
    db = sqlite3.connect(cfg.stanza_tenuta_db)
    pers = db.execute("SELECT DISTINCT persona, chi FROM righe WHERE nome = 'Marco Rossi'"
                      ).fetchall()
    db.close()
    verifica("le sue righe su disco passano alla persona di famiglia",
             pers == [(c.id, f"persona:{c.id}")], str(pers))
    r = sc.di(MARCO, "Grazie a tutti!")
    verifica("riconosciuto come familiare nelle righe dopo", r["chi"] == f"persona:{c.id}")
    # Il ritorno: contrari
    for nome_d, attesa in (("Carlo", "amministra"), ("Nicola", "minore")):
        ctx = contesto(sc, "Carlo", turno=10)
        tool_mod._conoscente_livello(ctx, "declassa", nome_d)
        ctx.turno = 11
        r = tool_mod._conoscente_livello(ctx, "declassa", nome_d)
        verifica(f"contrario: {nome_d} ({attesa}) non torna conoscente",
                 not r["ok"] and nome_d in voci.users, str(r))
    r = tool_mod._conoscente_livello(contesto(sc, "Bianca", "familiare"), "declassa",
                                     "Marco Rossi")
    verifica("contrario: un familiare non toglie un altro dalla famiglia",
             not r["ok"] and "Marco Rossi" in voci.users)
    ctx = contesto(sc, "Carlo", turno=20)
    tool_mod._conoscente_livello(ctx, "declassa", "Marco Rossi")
    ctx.turno = 21
    r = tool_mod._conoscente_livello(ctx, "declassa", "Marco Rossi")
    verifica("ritorno: Marco Rossi torna conoscente (stesso id), fuori dalla famiglia",
             r["ok"] and "Marco Rossi" not in voci.users and con.per_id(c.id) is not None, str(r))
    # Il minore: servono i tutori
    marco_presentato(sc, BAMBINO, "Pietro")
    con.risposta(scheda_a(hub, 1)[-1]["proposta"], "si", "carlo-id")
    ctx = contesto(sc, "Carlo", turno=30)
    r = tool_mod._conoscente_livello(ctx, "promuovi", "Pietro", nascita="2015-03-01")
    verifica("promozione di un minore senza tutori: li chiede", not r["ok"]
             and "genitore" in r["risposta_finale"])
    r = tool_mod._conoscente_livello(ctx, "promuovi", "Pietro", nascita="2015-03-01",
                                     tutori="Nicola")
    verifica("contrario: un tutore minorenne non va", not r["ok"])
    tool_mod._conoscente_livello(ctx, "promuovi", "Pietro", nascita="2015-03-01", tutori="Carlo")
    ctx.turno = 31
    r = tool_mod._conoscente_livello(ctx, "promuovi", "Pietro", nascita="2015-03-01",
                                     tutori="Carlo")
    p = voci.users.get("Pietro")
    verifica("promozione di un minore con nascita e tutori",
             r["ok"] and p is not None and p.nascita == "2015-03-01" and p.tutori == ["carlo-id"])
    # Un nome già in famiglia
    marco_presentato(sc, BIANCA2, "Bianca")
    con.risposta(scheda_a(hub, 1)[-1]["proposta"], "si", "carlo-id", "Bianca", "Verdi")
    ctx = contesto(sc, "Carlo", turno=40)
    tool_mod._conoscente_livello(ctx, "promuovi", "Bianca Verdi")
    ctx.turno = 41
    r = tool_mod._conoscente_livello(ctx, "promuovi", "Bianca Verdi")
    verifica("contrario: promuovere con un nome già in famiglia chiede un nome diverso",
             not r["ok"] and "nome diverso" in r["risposta_finale"]
             and voci.users["Bianca"].id == "bianca-id", str(r))
    verifica("misure: promossi e tornati, senza nomi",
             eventi(sc.mis, "promosso") and eventi(sc.mis, "declassato"))
    sc.chiudi()


# ─────────────────────────── 7. il server degli schermi ───────────────────────────
def prova_server():
    import httpx
    from pathlib import Path
    from calliope.schermi import ArchivioSchermi, Schermi
    from calliope.schermi.server import ServerSchermi
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from prova_schermi_pagina import porta_libera
    cfg = cfg_base(conoscenti_file=os.path.join(CARTELLA, "server.json"),
                   stanza_tenuta_db=os.path.join(CARTELLA, "server.db"))
    cfg.memory_db = str(Path(CARTELLA) / "schermi.db")
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db))
    port = porta_libera()
    srv = ServerSchermi(hub, "127.0.0.1", port).avvia()
    sc = Scena(cfg)
    try:
        base = f"http://127.0.0.1:{port}"

        def schermo(stanza, persona=None, nome=None):
            r = hub.archivio.nuova_richiesta()
            hub.archivio.abbina(r["codice"], stanza, persona, nome)
            return httpx.post(base + "/api/accedi",
                              headers={"Authorization": "Bearer " + r["richiesta"]}
                              ).json()["sessione"]
        carlo, bianca, stanza = (schermo("studio", "carlo-id", "Carlo"),
                                 schermo("cucina", "bianca-id", "Bianca"), schermo("sala"))

        def post(sess, dati):
            return httpx.post(base + "/api/conoscenti", json=dati, timeout=10,
                              headers={"X-Calliope-Sessione": sess})
        verifica("/api/conoscenti spenti: 404", post(carlo, {"azione": "no"}).status_code == 404)
        hub.conoscenti = sc.con
        marco_presentato(sc)
        pid = scheda_a(sc.hub, 1)[-1]["proposta"]
        verifica("/api/conoscenti senza sessione: 401",
                 post("x", {"azione": "si", "proposta": pid}).status_code == 401)
        verifica("contrario: da uno schermo di stanza 403",
                 post(stanza, {"azione": "si", "proposta": pid}).status_code == 403)
        verifica("contrario: dallo schermo personale di un familiare che non amministra 403",
                 post(bianca, {"azione": "si", "proposta": pid}).status_code == 403
                 and not sc.con.elenco())
        r = post(carlo, {"azione": "si", "proposta": pid, "nome": "Marcello", "cognome": "Neri",
                         "nota": "vicino di casa"})
        verifica("dallo schermo personale di chi amministra: salvato con il nome diverso",
                 r.status_code == 200 and sc.con.elenco()[0].nome == "Marcello"
                 and eventi(sc.mis, "conferma")[-1].get("nome_diverso") is True, r.text)
        verifica("una proposta già risposta: 410",
                 post(carlo, {"azione": "no", "proposta": pid}).status_code == 410)
    finally:
        srv.ferma()
        sc.chiudi()


# ─────────────────────────── 8. stato --turni e spento ───────────────────────────
def prova_stato_e_spento():
    righe = [{"tipo": "conoscenti", "evento": e} for e in
             ("gruppo_nuovo", "gruppo_nuovo", "proposta", "mandata", "conferma", "rifiuto")]
    righe.append({"tipo": "conoscenti", "evento": "proposta", "omonimo_famiglia": True})
    r = misure_mod.riassunto(righe)
    r["conoscenti_salvati"] = 1
    t = misure_mod.testo(r)
    verifica("stato --turni: la riga dei conoscenti con i conteggi",
             "Conoscenti: 1 salvati" in t and "proposte 2 (con omonimi 1" in t
             and "conferme 1, rifiuti 1, confermate 50 %" in t, t)
    cfg = cfg_base(stanza_conoscenti=False, conoscenti_file=os.path.join(CARTELLA, "no.json"))
    voci = Voci()
    st = Stanza(cfg, STTFinto(), registry=voci, misure=misure_mod.Misure(None),
                log=lambda m: None)
    verifica("contrario: spenti → nessun oggetto, nessun file",
             load_conoscenti_stanza(cfg, st, voci) is None
             and not os.path.exists(cfg.conoscenti_file)
             and con_mod.conta_file(cfg) is None)
    st.chiudi()
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "calliope.yaml"), encoding="utf-8") as f:
        y = f.read()
    verifica("calliope.yaml rigenerato con stanza_conoscenti (false) e i suoi campi",
             "stanza_conoscenti: false" in y and "conoscenti_scadenza_giorni: 180" in y)


# ─────────────────────────── 9. turni rivolti a Calliope e presenze (rifiniture) ─────────────
class Job:
    def __init__(self, e):
        self.e = e

    def result(self):
        return self.e


def miscela(pesi: dict) -> np.ndarray:
    """Un'impronta con i punteggi voluti contro le voci date ({indice: punteggio}); il resto
    su una voce che nessuno ha (23)."""
    v = np.zeros(DIM, dtype=np.float32)
    for i, p in pesi.items():
        v[i] = p
    v[23] = np.sqrt(max(0.0, 1.0 - float(v @ v)))
    return v


def ciclo_per(sc: "Scena | None", cfg, voci):
    from calliope.ciclo import Ciclo, Servizi
    from calliope.speaker_id import SpeakerContext
    voci.cfg = cfg
    voci.adapt = lambda *a: False          # l'impronta non si aggiorna nelle prove
    sctx = SpeakerContext(voci)
    corsia = SimpleNamespace(satellite_id=1, conv=None, nome="satellite cucina", chiave="sat:1")
    ciclo = Ciclo(Servizi(cfg, registry=voci, stanza=sc.st if sc is not None else None),
                  corsia, None, SimpleNamespace(_current_voice_path=None), sctx, None, None,
                  None, None, None)
    ciclo.listener = SimpleNamespace(_ultima=(SimpleNamespace(satellite={"id": 1}), None),
                                     started_at=time.monotonic() - 2.5,
                                     ended_at=time.monotonic() - 0.3)
    ciclo.rule = lambda r: None
    return ciclo, sctx


def turno(ciclo, sctx, emb, testo="Calliope, che ore sono?", voce_s=2.5, prev=None,
          in_session=False):
    from calliope.ciclo import Turno
    sctx.current_speaker = prev
    t = Turno(voiced_s=voce_s, in_session=in_session, emb_job=Job(emb), prev_how=None)
    t.text = testo
    ciclo.rec = {}
    ciclo._chi_parla(t)
    return t


def nota_turno(cfg, voci, sctx) -> str:
    from calliope.brain import Brain
    b = Brain.__new__(Brain)
    b.cfg, b.last_rules = cfg, []
    b.tool_ctx = ToolContext(cfg=cfg, speakers=voci, speaker_ctx=sctx, speaker=None)
    return b._turn_context()[0]["content"]


def prova_turni_e_presenze():
    cfg = cfg_base(conoscenti_file=os.path.join(CARTELLA, "turni.json"),
                   stanza_tenuta_db=os.path.join(CARTELLA, "turni.db"))
    sc = Scena(cfg)
    con, hub, voci, st = sc.con, sc.hub, sc.voci, sc.st
    marco_presentato(sc)
    con.risposta(scheda_a(hub, 1)[-1]["proposta"], "si", "carlo-id", "Marco", "Rossi",
                 "collega di Carlo")
    c = con.elenco()[0]
    chiave = f"conoscente:{c.id}"
    # Marco in cucina, riconosciuto come conoscente; poi Carlo dice il codice del cancello
    r = sc.di(MARCO, "Eccomi, ho portato le pizze.")
    verifica("nella stanza la riga del conoscente apre la sua presenza",
             r["chi"] == chiave and any(p["persona"] == chiave for p in st.presenti(1)))
    sc.di(CARLO, "Il codice del cancello nuovo è quattro cinque uno due.")
    ciclo, sctx = ciclo_per(sc, cfg, voci)
    # 1. Il conoscente parla a Calliope (turno col nome)
    t = turno(ciclo, sctx, voce(MARCO, 0.03, seme=1))
    rec = ciclo.rec
    verifica("turno: la voce del conoscente → chi parla «Marco Rossi», conoscente",
             sctx.conoscente == {"id": c.id, "nome": "Marco Rossi", "nota": "collega di Carlo"},
             str(sctx.conoscente))
    verifica("…ma resta un ospite: nessun chi parla, livello ospite, nessun nome di casa",
             sctx.current_speaker is None and sctx.current_level == "ospite"
             and t.speaker_name is None and rec.get("livello") == "ospite"
             and rec["voce"]["nome"] is None)
    verifica("nel registro dei turni solo «conoscente: true» (mai il nome: niente turni su "
             "disco per un conoscente)", rec["voce"].get("conoscente") is True
             and "Marco" not in json.dumps(rec, ensure_ascii=False))
    cons = conserva_mod.Conservazione(cfg, voci, log=lambda m: None)
    verifica("le parole del suo turno non restano (come un ospite)",
             not cons.testo_turno(dict(rec, testo="Calliope, che ore sono?")))
    nota = nota_turno(cfg, voci, sctx)
    verifica("dati del turno: «persona: Marco Rossi (conoscente, collega di Carlo)… è un "
             "ospite»", "persona: Marco Rossi (conoscente, collega di Carlo), riconosciuto "
             "dalla voce: non è della famiglia, è un ospite." in nota, nota[:300])
    r = st.registro(1).righe()[-1]
    verifica("la frase del turno nella stanza col suo nome, la nota e «→ Calliope»",
             r["chi"] == chiave and r["nome"] == "Marco Rossi" and r["sicurezza"] == "voce"
             and r.get("nota") == "collega di Carlo" and r["rivolta"] == "si"
             and ctx_mod.etichetta(r) == "Marco Rossi (collega di Carlo), conoscente → Calliope",
             str(r))
    ctx_g = ToolContext(cfg=cfg, speakers=voci, speaker_ctx=sctx, speaker=None, stanza=st)
    ctx_g.attesa, ctx_g.turno = None, 1
    rc = tool_stanza._stanza_cerca(ctx_g, parole="gita")
    verifica("permessi invariati: il conoscente non può cercare nella stanza (ospite)",
             not rc.get("ok", True) and not rc.get("trovato"), str(rc))
    # 2. La famiglia vince sempre
    turno(ciclo, sctx, voce(CARLO, 0.03, seme=2))
    verifica("contrario: la voce di Carlo resta Carlo (amministra), nessun conoscente",
             sctx.current_speaker == "Carlo" and sctx.conoscente is None
             and sctx.current_level == "amministra")
    turno(ciclo, sctx, miscela({CARLO: 0.44, MARCO: 0.85}))
    verifica("contrario: Carlo nella zona grigia (0,44) e Marco a 0,85 fuori conversazione → "
             "ospite senza nome (la famiglia nella zona grigia vince sul conoscente)",
             sctx.current_speaker is None and sctx.conoscente is None)
    turno(ciclo, sctx, miscela({CARLO: 0.44, MARCO: 0.85}), prev="Carlo", in_session=True)
    verifica("contrario: la stessa frase nella conversazione di Carlo → Carlo (familiare)",
             sctx.current_speaker == "Carlo" and sctx.conoscente is None
             and sctx.current_level == "familiare")
    turno(ciclo, sctx, miscela({BIANCA: 0.33, MARCO: 0.38}))
    verifica("contrario: Marco a meno del margine da Bianca (0,38 contro 0,33) → nessuno",
             sctx.current_speaker is None and sctx.conoscente is None)
    turno(ciclo, sctx, voce(MARCO, 0.03, seme=3), voce_s=0.6)
    verifica("contrario: frase breve (0,6 s) → nessun conoscente", sctx.conoscente is None)
    turno(ciclo, sctx, voce(15, 0.03, seme=4))
    verifica("contrario: una voce di nessuno → ospite senza nome",
             sctx.conoscente is None and sctx.current_speaker is None)
    t = turno(ciclo, sctx, voce(MARCO, 0.03, seme=5))
    sctx_vecchio = sctx.conoscente
    t2 = turno(ciclo, sctx, voce(BIANCA, 0.03, seme=6))
    verifica("contrario: il conoscente vale una frase sola (poi Bianca, senza etichetta)",
             sctx_vecchio is not None and sctx.conoscente is None
             and sctx.current_speaker == "Bianca")
    ciclo2, sctx2 = ciclo_per(None, cfg, voci)
    turno(ciclo2, sctx2, voce(MARCO, 0.03, seme=7))
    verifica("contrario: senza la stanza (né i conoscenti) → ospite come prima",
             sctx2.conoscente is None and "conoscente" not in ciclo2.rec["voce"])
    verifica("contrario: un ospite resta «un ospite, non riconosciuto dalla voce»",
             "persona: un ospite, non riconosciuto dalla voce." in nota_turno(cfg, voci, sctx2))
    # 3. Le presenze: anche il conoscente conta per «chi c'era»
    pres = {p["persona"]: p["nome"] for p in st.presenti(1)}
    verifica("presenze: il conoscente presente in cucina dopo il suo turno",
             pres.get(chiave) == "Marco Rossi", str(pres))
    blocco = ctx_mod._presenti(st, 1)
    verifica("il blocco della stanza: «presenti: … Marco Rossi (conoscente)»",
             "Marco Rossi (conoscente)" in blocco and "Carlo" in blocco, blocco)
    prima = sorted(p["persona"] for p in st.presenti(1))
    sc.di(15, "Io vado, ciao.")
    r = next(x for x in st.registro(1).righe() if x.get("testo") == "Io vado, ciao.")
    verifica("contrario: una voce di nessuno non ha presenza",
             r["chi"] == "ignoto" and sorted(p["persona"] for p in st.presenti(1)) == prima,
             f"{r}")
    st._presenze_su_disco(sempre=True)
    st.tenuta.attendi()
    db = sqlite3.connect(cfg.stanza_tenuta_db)
    n = db.execute("SELECT COUNT(*) FROM presenze WHERE persona = ?", (chiave,)).fetchone()[0]
    db.close()
    verifica("le presenze del conoscente anche su disco (tenuta)", n >= 1)
    st.tenuta.conoscenti = None
    st.tenuta.ruota()
    st.tenuta.conoscenti = con
    db = sqlite3.connect(cfg.stanza_tenuta_db)
    n = db.execute("SELECT COUNT(*) FROM presenze WHERE persona = ?", (chiave,)).fetchone()[0]
    db.close()
    verifica("contrario: la rotazione senza i conoscenti legati non tocca le sue presenze", n >= 1)
    chi_z = cerca_mod.Chi(pid="zoe-id", nome="Zoe", sat=None)
    es = cerca_mod.cerca(st, cfg, chi_z, "cancello", adesso=sc.t + 3 * 86400)
    verifica("contrario: un adulto che non c'era non trova il codice", es.esito == "niente")
    # La promozione: le sue presenze passano con lui, e cerca dove c'era già
    con.promuovi(c.id)
    st.tenuta.attendi()
    db = sqlite3.connect(cfg.stanza_tenuta_db)
    pp = dict(db.execute("SELECT persona, COUNT(*) FROM presenze WHERE persona IN (?, ?) "
                         "GROUP BY persona", (chiave, c.id)).fetchall())
    db.close()
    verifica("promosso: le presenze passano a lui (memoria e disco)",
             pp.get(c.id, 0) >= 1 and chiave not in pp
             and any(p[0] == st.chiave_sat(1) for p in st.presenze(c.id))
             and not st.presenze(chiave), str(pp))
    es = cerca_mod.cerca(st, cfg, cerca_mod.Chi(pid=c.id, nome="Marco Rossi", sat=None),
                         "cancello", adesso=sc.t + 3 * 86400)
    verifica("promosso: trova il codice detto in cucina mentre c'era da conoscente",
             es.esito == "trovato" and "cancello" in es.testo, es.esito)
    con.declassa(voci.users["Marco Rossi"])
    verifica("tornato conoscente: le presenze tornano alla chiave del conoscente",
             st.presenze(chiave) and not [p for p in st.presenze(c.id)])
    # Dimenticato: via anche le presenze (memoria e disco)
    con.dimentica(c.id)
    st.tenuta.attendi()
    db = sqlite3.connect(cfg.stanza_tenuta_db)
    n = db.execute("SELECT COUNT(*) FROM presenze WHERE persona LIKE 'conoscente:%'"
                   ).fetchone()[0]
    db.close()
    verifica("dimenticato: le sue presenze via, in memoria e su disco",
             n == 0 and not st.presenze(chiave)
             and chiave not in [p["persona"] for p in st.presenti(1)])
    # Omonimia: una conoscente che si chiama come Bianca di casa non diventa mai lei
    marco_presentato(sc, BIANCA2, "Bianca")
    con.risposta(scheda_a(hub, 1)[-1]["proposta"], "si", "carlo-id", "Bianca", "Verdi")
    turno(ciclo, sctx, voce(BIANCA2, 0.03, seme=8), testo="Calliope, cosa c'è in agenda?")
    nota = nota_turno(cfg, voci, sctx)
    verifica("omonimia: la voce della conoscente Bianca Verdi → conoscente, mai Bianca di casa",
             sctx.conoscente and sctx.conoscente["nome"] == "Bianca Verdi"
             and sctx.current_speaker is None and sctx.current_level == "ospite"
             and "persona: Bianca Verdi (conoscente)" in nota
             and "persona: Bianca," not in nota, nota[:200])
    r = st.registro(1).righe()[-1]
    verifica("omonimia: nella stanza la riga è della conoscente, non di bianca-id",
             r["chi"].startswith("conoscente:") and r.get("persona") is None
             and ctx_mod._presenti(st, 1).count("Bianca Verdi (conoscente)") == 1)
    turno(ciclo, sctx, voce(BIANCA, 0.03, seme=9))
    verifica("omonimia, contrario: la voce di Bianca di casa resta Bianca (familiare)",
             sctx.current_speaker == "Bianca" and sctx.conoscente is None)
    sc.chiudi()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    prova_regola()
    prova_proposta()
    prova_omonimie()
    prova_contrari()
    prova_permessi_e_scadenza()
    prova_livello()
    prova_server()
    prova_stato_e_spento()
    prova_turni_e_presenze()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    return 1 if errori else 0


if __name__ == "__main__":
    raise SystemExit(main())
