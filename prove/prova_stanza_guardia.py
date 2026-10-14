"""
Prova a secco del guardiano a posteriori della stanza (14/10/2026, passo 6 della conversazione di
stanza: progetto docs/ricerche/2026-10-13-conversazione-di-stanza.md § 3.9 e § 6 riga 6,
decisione 0029 punto 4; calliope/stanza/guardia.py), dietro `stanza_guardia`.

Con un giudice finto (niente modello):

- quali righe: quelle di un minore (voce o zona grigia) e quelle dette con un minore presente,
  dopo l'attesa e a stanza quieta, a blocchi con il contesto intorno; mai Calliope, la TV, le
  frasi rivolte a Calliope (solo contesto);
- i filtri dopo il giudizio: scherzo, gioco e TV non sono segnali; acuto solo con l'attribuzione
  sicura (zona grigia, parole incerte, righe fuori dal blocco, autolesionismo non del minore →
  dubbio);
- ombra: nessun avviso, solo misure senza parole né nomi, con ciò che sarebbe successo;
- attiva: avviso al tutore solo sullo schermo personale (mai a voce: già «detto» nella tabella),
  senza le parole, col rimando a cercare; tetto al giorno, la stessa categoria non ripetuta, due
  dubbi in giorni diversi → un avviso non urgente;
- carico: niente con la voce occupata e prima della quiete, tetto di giudizi all'ora con la coda
  che aspetta, giudizio guasto riprovato e poi buttato;
- pausa (ospiti): niente raccolta né giudizi, i blocchi di prima aspettano la ripresa;
  «dimentica»: blocchi in coda buttati, e un giudizio in corso buttato;
- il giudice vero (`GiudiceModello`, `Guardiano.chiedi_json`) con un client HTTP finto: stesso
  modello e stesse opzioni del rilevatore, il prompt nella finestra di 2048 token;
- `calliope stato --turni` (sezione) e `calliope stato --guardia` (elenco, --falso/--vero);
- (14/10 sera) la ripresa dal disco dopo un riavvio, con `stanza.db` vero e tre «avvii»: le righe
  non giudicate si riprendono, le giudicate (diario) no; contrari: dimenticate, oltre il limite,
  non assestate, pausa, prima del diario, ripresa spenta, senza tenuta;
- (14/10 sera) la modalità gioco: il gioco dichiarato nel prompt, la minaccia di un altro in
  gioco → dubbio, l'autolesionismo serio del minore resta acuto; contrari: gioco chiuso, in
  un'altra stanza, senza giochi; i periodi sul diario dopo un riavvio; `Giochi.in_corso`.

Contrari: spenta (nessun thread, nessun giudizio), nessun minore, solo adulti, minore in un'altra
stanza, TV, scherzi e videogiochi, pausa, dimentica, tetto, voce occupata, righe troppo recenti.
Nomi di fantasia (Carlo amministra ed è tutore di Nicola, 14 anni; Bianca è di famiglia). ~2 s.
"""

import contextlib
import datetime
import io
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope import minori as minori_mod  # noqa: E402
from calliope.config import VALIDATORI, Config  # noqa: E402
from calliope.guardiano import Guardiano  # noqa: E402
from calliope.stanza import guardia as gm  # noqa: E402
from calliope.stanza import load_guardia  # noqa: E402
from calliope.stanza import misure as misure_mod  # noqa: E402
from calliope.stanza.ascolto import Stanza  # noqa: E402

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
        self.fascia = None


class Voci:
    def __init__(self):
        self.users = {"Carlo": Prof("carlo-id", "Carlo", admin=True),
                      "Nicola": Prof("nicola-id", "Nicola", "2012-05-01",
                                     tutori=["carlo-id"]),
                      "Bianca": Prof("bianca-id", "Bianca")}

    def get(self, n):
        return self.users.get(n)


CARTELLA = tempfile.mkdtemp(prefix="calliope-guardia-")
ORA = time.time()
LOG: list = []


def cfg_base(**k) -> Config:
    c = Config()
    c.stanza, c.stanza_guardia = "ombra", "ombra"
    c.stanza_guardia_quiete_s = 0.0
    c.turn_log_dir = os.path.join(CARTELLA, k.pop("registro", "registro"))
    c.memory_db = os.path.join(CARTELLA, "memoria.db")
    for a, v in k.items():
        setattr(c, a, v)
    return c


def stanza_nuova(cfg):
    st = Stanza(cfg, STTFinto(), registry=Voci(), misure=misure_mod.Misure(cfg.turn_log_dir),
                log=lambda m: None)
    st._info[1] = {"nome": "satellite cucina", "stanza": "cucina", "canale": "satellite"}
    st._info[2] = {"nome": "satellite sala", "stanza": "sala", "canale": "satellite"}
    return st


def riga(st, sat, testo, fine, nome=None, sicurezza="voce", chi=None, p_min=None,
         rivolta="ignoto"):
    prof = Voci().get(nome) if nome else None
    return st.registro(sat).aggiungi(
        "riga", segmento=None, versione=1, inizio=round(fine - 3, 3), fine=round(fine, 3),
        testo=testo, chi=chi or (f"persona:{prof.id}" if prof else "ignoto"), nome=nome,
        sicurezza=sicurezza if nome else "nessuna", p_min=p_min, rivolta=rivolta,
        minore=nome == "Nicola").seq


class Giudice:
    """Il giudice finto: decide dalle parole delle righe da giudicare, come farebbe il modello
    (i casi), e ricorda che cosa ha visto."""

    REGOLE = (("sei morto", "ACUTO", "pericolo", "serio"),       # il modello che sbaglia
              ("mi butto giù", "ACUTO", "autolesionismo", "non_chiaro"),
              ("mi picchia", "ACUTO", "abuso", "serio"),
              ("se lo dici alla mamma", "ACUTO", "abuso", "serio"),
              ("non voglio più mangiare", "ACUTO", "autolesionismo", "serio"),
              ("voglio morire", "ACUTO", "autolesionismo", "serio"),
              ("ti ammazzo se perdi", "ACUTO", "pericolo", "gioco"),
              ("mi sparo", "ACUTO", "autolesionismo", "scherzo"),
              ("ostaggi", "ACUTO", "pericolo", "tv"),
              ("sparire", "DUBBIO", "autolesionismo", "non_chiaro"))

    def __init__(self, guasto=0, durante=None):
        self.visti: list = []
        self.guasto = guasto
        self.durante = durante

    def __call__(self, b):
        self.visti.append(b)
        if self.durante is not None:
            self.durante()
        if self.guasto:
            self.guasto -= 1
            return None
        for i, r in enumerate(b.giudicate, 1):
            t = str(r.get("testo") or "").lower()
            for parola, liv, cat, ctx in self.REGOLE:
                if parola in t:
                    return gm.leggi_esito({"livello": liv, "categoria": cat, "contesto": ctx,
                                           "righe": [i]})
        return gm.leggi_esito({"livello": "NIENTE", "categoria": "nessuna",
                               "contesto": "serio", "righe": []})


class AvvisiFinti:
    def __init__(self):
        self.mandati: list = []

    def solo_schermo(self, minore, tipo, testo, urgente=False, registry=None, **extra):
        # Dal 14/10 anche l'origine e il riferimento (l'id del segnale) dell'avviso
        self.mandati.append((minore.id, tipo, testo, urgente))
        self.extra = extra
        return 1


def guardia(cfg, st, giudice=None, avvisi=None, occupato=(), gioco=None):
    return gm.Guardia(cfg, st, giudice or Giudice(), avvisi=avvisi, occupato=occupato,
                      log=LOG.append, avvia=False, gioco=gioco)


def misure_guardia(cfg) -> list:
    return [r for r in misure_mod.leggi(cfg.turn_log_dir) if r.get("tipo") == "guardia"]


def file_misure(cfg) -> str:
    out = ""
    for f in sorted(os.listdir(cfg.turn_log_dir)) if os.path.isdir(cfg.turn_log_dir) else []:
        with open(os.path.join(cfg.turn_log_dir, f), encoding="utf-8") as fh:
            out += fh.read()
    return out


# ─────────────────────────── 0. spenta e configurazione ───────────────────────────
def prova_spenta():
    c = Config()
    verifica("di serie spenta, attesa 120 s, 30 giudizi all'ora, 1 avviso al giorno",
             c.stanza_guardia == "spenta" and c.stanza_guardia_attesa_s == 120.0
             and c.stanza_guardia_giudizi_ora == 30 and c.stanza_guardia_avvisi_giorno == 1)
    v = VALIDATORI["stanza_guardia"]
    try:
        v("accesa")
        rifiuta = False
    except ValueError:
        rifiuta = True
    verifica("validatore: spenta, ombra, attiva sì; «accesa» no",
             v("Ombra") == "ombra" and v("attiva") == "attiva" and rifiuta)
    yaml_txt = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "calliope.yaml"), encoding="utf-8").read()
    verifica("calliope.yaml rigenerato con stanza_guardia: spenta",
             "stanza_guardia: spenta" in yaml_txt and "stanza_guardia_giudizi_ora: 30" in yaml_txt)
    cfg = cfg_base(stanza_guardia="spenta", registro="r0")
    st = stanza_nuova(cfg)
    verifica("contrario: spenta → load_guardia None (nessun thread)",
             load_guardia(cfg, st, guardiano=None) is None)
    verifica("contrario: stanza assente → None",
             load_guardia(cfg_base(), None) is None)
    verifica("contrario: minori spenti → None",
             load_guardia(cfg_base(minori_enabled=False), st) is None)
    st._sentita("nicola-id", "Nicola", 1, ORA - 700)
    riga(st, 1, "Il mister mi picchia quando sbaglio.", ORA - 600, "Nicola")
    g = guardia(cfg, st)
    verifica("contrario: spenta → nessun giudizio, niente in coda",
             g.giro(ORA) == 0 and not g.giudice.visti and g.in_coda() == 0)
    cfg_o = cfg_base(registro="r0b")
    g2 = load_guardia(cfg_o, st, guardiano=Guardiano(cfg_o, log=lambda m: None),
                      log=lambda m: None)
    verifica("ombra: load_guardia con il rilevatore → Guardia col giudice del modello",
             isinstance(g2, gm.Guardia) and isinstance(g2.giudice, gm.GiudiceModello)
             and g2._thread is not None)
    g2.chiudi()
    cfg_n = cfg_base(guardiano_pericolo=False, registro="r0c")
    verifica("contrario: rilevatore spento (guardiano_pericolo: false) → None",
             load_guardia(cfg_n, st, guardiano=Guardiano(cfg_n, log=lambda m: None),
                          log=lambda m: None) is None)
    st.chiudi()


# ─────────────────────────── 1. quali righe ───────────────────────────
def prova_righe():
    cfg = cfg_base(registro="r1")
    st = stanza_nuova(cfg)
    # Solo adulti in cucina: niente
    riga(st, 1, "Domani chiamo l'idraulico.", ORA - 900, "Carlo")
    riga(st, 1, "Ti ammazzo se non porti fuori il cane.", ORA - 890, "Bianca")
    g = guardia(cfg, st)
    g.giro(ORA)
    verifica("contrario: solo adulti (nessun minore presente) → nessun blocco",
             not g.giudice.visti and g.in_coda() == 0)
    # Nicola presente in sala, non in cucina: le righe della cucina non si guardano
    st._sentita("nicola-id", "Nicola", 2, ORA - 800)
    riga(st, 1, "Bianca, se lo dici alla mamma ti faccio male.", ORA - 780, "Carlo")
    g.giro(ORA)
    verifica("contrario: il minore è in un'altra stanza → la cucina non si guarda",
             not g.giudice.visti)
    # Il minore che parla in sala, la TV e Calliope intorno
    riga(st, 2, "Ostaggi liberati stanotte al confine, dice il telegiornale.", ORA - 790,
         chi="tv")
    st.detto(2, "Sono le cinque e un quarto.", ORA - 785, ORA - 784)
    riga(st, 2, "Che ore sono?", ORA - 787, "Nicola", rivolta="si")
    riga(st, 2, "Oggi a scuola abbiamo fatto la verifica di storia.", ORA - 770, "Nicola")
    riga(st, 2, "Com'è andata?", ORA - 765, "Carlo")
    n = g.giro(ORA)
    b = g.giudice.visti[0] if g.giudice.visti else None
    testi = [r.get("testo") for r in (b.giudicate if b else [])]
    verifica("un minore presente in sala: un blocco giudicato", n == 1 and b is not None,
             f"n={n}")
    verifica("da giudicare: la riga di Nicola e quella di Carlo con Nicola presente",
             testi == ["Oggi a scuola abbiamo fatto la verifica di storia.", "Com'è andata?"],
             str(testi))
    p = gm.prompt(b) if b else ""
    verifica("la TV non è nel prompt, Calliope e la frase a Calliope sono contesto col trattino",
             "Ostaggi" not in p and "- Calliope: Sono le cinque" in p
             and "- Nicola (minore) → Calliope: Che ore sono?" in p
             and "[1] Nicola (minore): Oggi a scuola" in p and "[2] Carlo: Com'è andata?" in p,
             p[-400:])
    verifica("il prompt nomina il minore e la conversazione di famiglia",
             "È presente un minore: Nicola" in p and "videogiochi" in p)
    verifica("ombra, niente: nessun avviso; misura con il livello e senza parole",
             any(r.get("livello") == "niente" and r.get("righe") == 2 for r in misure_guardia(cfg))
             and "verifica di storia" not in file_misure(cfg) and "Nicola" not in file_misure(cfg))
    verifica("le righe già raccolte non si rigiudicano", g.giro(ORA) == 0)
    st.chiudi()


# ─────────────────────────── 2. attesa, quiete e carico ───────────────────────────
def prova_carico():
    cfg = cfg_base(registro="r2")
    st = stanza_nuova(cfg)
    st._sentita("nicola-id", "Nicola", 1, ORA - 100)
    riga(st, 1, "Il mister mi picchia quando sbaglio.", ORA - 30, "Nicola")
    g = guardia(cfg, st)
    g.giro(ORA)
    verifica("contrario: righe di 30 s fa (sotto stanza_guardia_attesa_s) → non ancora",
             not g.giudice.visti and g.in_coda() == 0)
    # Assestate, ma lo scambio continua (una riga di 10 s fa): si aspetta che taccia
    riga(st, 1, "Ok ragazzi, cambiamo argomento.", ORA + 200, "Carlo")
    g.giro(ORA + 300)
    verifica("contrario: lo scambio continua → si aspetta", not g.giudice.visti)
    g.giro(ORA + 400)
    verifica("a stanza quieta il blocco si giudica", len(g.giudice.visti) == 1)
    # La voce occupata: niente giudizi, la coda aspetta
    occupata = [True]
    g2 = guardia(cfg_base(registro="r2b"), st, occupato=[lambda: occupata[0]])
    riga(st, 1, "Non voglio più mangiare, mi vedo grassa.", ORA + 500, "Nicola")
    g2.raccogli(ORA + 900)
    n0 = g2.giro(ORA + 900)
    verifica("contrario: voce occupata (una risposta in corso) → nessun giudizio, in coda",
             n0 == 0 and g2.in_coda() >= 1)
    occupata[0] = False
    g2.cfg.stanza_guardia_quiete_s = 30.0
    verifica("contrario: voce libera da meno di stanza_guardia_quiete_s → ancora niente",
             g2.giro(ORA + 900) == 0)
    g2._libera_da -= 31
    verifica("voce ferma da abbastanza → giudicato", g2.giro(ORA + 900) >= 1)
    # Il tetto all'ora: 2 giudizi, gli altri aspettano
    cfg3 = cfg_base(registro="r2c", stanza_guardia_giudizi_ora=2)
    st3 = stanza_nuova(cfg3)
    st3._sentita("nicola-id", "Nicola", 1, ORA - 10000)
    for k in range(4):        # quattro blocchi separati da silenzi lunghi
        riga(st3, 1, f"Partita numero {k} finita.", ORA - 9000 + k * 1000, "Nicola")
    g3 = guardia(cfg3, st3)
    n = g3.giro(ORA)
    verifica("tetto di 2 giudizi all'ora: 2 giudicati, 2 in coda", n == 2 and g3.in_coda() == 2,
             f"n={n} coda={g3.in_coda()}")
    g3._fatti.clear()
    verifica("dopo un'ora la coda si svuota", g3.giro(ORA) == 2 and g3.in_coda() == 0)
    # Guasto: riprovato, poi buttato
    cfg4 = cfg_base(registro="r2d")
    st4 = stanza_nuova(cfg4)
    st4._sentita("nicola-id", "Nicola", 1, ORA - 1000)
    riga(st4, 1, "Il mister mi picchia quando sbaglio.", ORA - 900, "Nicola")
    g4 = guardia(cfg4, st4, giudice=Giudice(guasto=5))
    g4.giro(ORA)
    es = [r.get("esito") for r in misure_guardia(cfg4)]
    verifica(f"giudizio guasto riprovato {gm.TENTATIVI} volte, poi buttato e contato",
             es.count("guasto") == gm.TENTATIVI and g4.in_coda() == 0, str(es))
    for s in (st, st3, st4):
        s.chiudi()


# ─────────────────────────── 3. filtri e livelli ───────────────────────────
def scena_uno(cfg, testo, nome="Nicola", sicurezza="voce", p_min=None, chi=None,
              presente=True, giudice=None, avvisi=None):
    st = stanza_nuova(cfg)
    if presente:
        st._sentita("nicola-id", "Nicola", 1, ORA - 1000)
    riga(st, 1, "Dai, giochiamo ancora una partita.", ORA - 910, "Carlo")
    riga(st, 1, testo, ORA - 900, nome, sicurezza=sicurezza, p_min=p_min, chi=chi)
    g = guardia(cfg, st, giudice=giudice, avvisi=avvisi)
    g.giro(ORA)
    m = [r for r in misure_guardia(cfg) if r.get("esito") == "giudicato"]
    return st, g, (m[-1] if m else {})


def prova_filtri():
    _, _, m = scena_uno(cfg_base(registro="r3a"), "Il mister mi picchia quando sbaglio.")
    verifica("minore che parla, abuso serio → acuto, ombra (avrebbe avvisato)",
             m.get("livello") == "acuto" and m.get("categoria") == "abuso"
             and m.get("avviso") == "ombra" and m.get("modo_minore") == "parla"
             and m.get("minori") == ["nicola-id"], str(m))
    _, _, m = scena_uno(cfg_base(registro="r3b"), "Ti ammazzo se perdi, dai che vinciamo!")
    verifica("contrario: videogioco («ti ammazzo se perdi», contesto gioco) → niente",
             m.get("livello") == "niente" and m.get("modello") == "acuto"
             and m.get("motivo") == "gioco" and not m.get("avviso"), str(m))
    _, _, m = scena_uno(cfg_base(registro="r3c"), "Che palle sta verifica, mi sparo.")
    verifica("contrario: scherzo («mi sparo») → niente", m.get("livello") == "niente"
             and m.get("motivo") == "scherzo", str(m))
    _, _, m = scena_uno(cfg_base(registro="r3d"), "Gli ostaggi sono ancora nel palazzo.",
                        nome=None)
    verifica("contrario: la TV (contesto tv) → niente", m.get("livello") == "niente"
             and m.get("motivo") == "tv", str(m))
    _, _, m = scena_uno(cfg_base(registro="r3e"), "Il mister mi picchia quando sbaglio.",
                        sicurezza="grigia", presente=False)
    verifica("zona grigia del minore → dubbio (voce_incerta)", m.get("livello") == "dubbio"
             and m.get("motivo") == "voce_incerta", str(m))
    _, _, m = scena_uno(cfg_base(registro="r3f"), "Il mister mi picchia quando sbaglio.",
                        p_min=0.3)
    verifica("parola incerta (p_min sotto 0,5) → dubbio", m.get("livello") == "dubbio"
             and m.get("motivo") == "parole_incerte", str(m))
    _, _, m = scena_uno(cfg_base(registro="r3g"), "Se lo dici alla mamma ti faccio male.",
                        nome=None)
    verifica("una voce sconosciuta minaccia con il minore presente → acuto (presente)",
             m.get("livello") == "acuto" and m.get("modo_minore") == "presente", str(m))
    _, _, m = scena_uno(cfg_base(registro="r3h"), "Certe sere voglio morire anch'io.", "Carlo")
    verifica("autolesionismo detto da un adulto col minore presente → dubbio (non_del_minore)",
             m.get("livello") == "dubbio" and m.get("motivo") == "non_del_minore", str(m))

    class FuoriBlocco(Giudice):
        def __call__(self, b):
            return gm.leggi_esito({"livello": "ACUTO", "categoria": "abuso",
                                   "contesto": "serio", "righe": [7]})
    _, _, m = scena_uno(cfg_base(registro="r3i"), "Il mister mi picchia quando sbaglio.",
                        giudice=FuoriBlocco())
    verifica("righe del segnale fuori dal blocco → dubbio (righe)",
             m.get("livello") == "dubbio" and m.get("motivo") == "righe", str(m))
    st, _, m = scena_uno(cfg_base(registro="r3j"), "Mi sa che voglio sparire per un po'.")
    verifica("dubbio del modello: nessun avviso", m.get("livello") == "dubbio"
             and not m.get("avviso"), str(m))
    st.chiudi()
    verifica("leggi_esito: contrari (livello sconosciuto, non un dict) → None; valori puliti",
             gm.leggi_esito({"livello": "FORSE"}) is None and gm.leggi_esito("x") is None
             and gm.leggi_esito({"livello": "ACUTO", "categoria": "boh", "contesto": "?",
                                 "righe": ["2", "x"]}) == {
                 "livello": "acuto", "categoria": "nessuna", "contesto": "non_chiaro",
                 "righe": [2]})
    verifica("nel log solo livello, categoria e stanza, mai le parole",
             any("[GUARDIA] cucina: acuto (abuso)" in x for x in LOG)
             and not any("picchia" in x or "mamma" in x for x in LOG))


# ─────────────────────────── 4. attiva: avvisi ───────────────────────────
class Hub:
    def __init__(self):
        self.schede = []

    def invia(self, card, mittente, forza=False):
        self.schede.append((card, mittente, forza))


def prova_attiva():
    cfg = cfg_base(registro="r4", stanza_guardia="attiva")
    hub = Hub()
    av = minori_mod.Avvisi(os.path.join(CARTELLA, "avvisi.db"), schermi=hub, registry=Voci(),
                           log=lambda m: None)
    st, g, m = scena_uno(cfg, "Il mister mi picchia quando sbaglio.", avvisi=av)
    verifica("attiva, acuto → avviso mandato", m.get("avviso") == "mandato", str(m))
    righe_db = av.db.execute("SELECT tutore, minore, tipo, testo, urgente, detto FROM "
                             "avvisi_tutori").fetchall()
    testo = righe_db[0][3] if righe_db else ""
    verifica("l'avviso va al tutore (Carlo), tipo sicurezza_stanza, urgente",
             len(righe_db) == 1 and righe_db[0][0] == "carlo-id" and righe_db[0][1] == "nicola-id"
             and righe_db[0][2] == "sicurezza_stanza" and righe_db[0][4] == 1, str(righe_db))
    verifica("solo sullo schermo: già «detto» (la voce non lo annuncia mai)",
             righe_db and righe_db[0][5] is not None and av.da_dire("carlo-id") == [])
    verifica("la scheda personale del tutore, forzata", len(hub.schede) == 1
             and hub.schede[0][1].persona == "carlo-id" and hub.schede[0][2] is True)
    # 14/10 (ramo avvisi-data): l'origine, il riferimento al segnale e la data sulla scheda
    rr = av.db.execute("SELECT origine, rif, come FROM avvisi_tutori").fetchone()
    ident = m.get("id")
    verifica("l'avviso ha l'origine (rilettura in cucina), il riferimento al segnale e «schermo»",
             rr == ("dalla rilettura della conversazione in cucina", f"guardia:{ident}",
                    "schermo"), f"{rr} {ident}")
    verifica("la scheda dice quando è nato e da dove",
             "dalla rilettura della conversazione in cucina." in hub.schede[0][0].get("testo", ""),
             hub.schede[0][0].get("testo"))
    verifica("senza le parole del minore, con dove, quando, l'argomento e il rimando a cercare",
             "picchia" not in testo and "mister" not in testo and "in cucina verso le" in testo
             and "Nicola ha parlato di qualcuno che potrebbe fargli del male" in testo
             and "chiedimi «cosa ha detto Nicola in cucina" in testo
             and "non ho detto niente a nessuno" in testo, testo)
    # Stessa categoria entro 24 ore → ripetuto; altra categoria lo stesso giorno → tetto
    riga(st, 1, "Il mister mi picchia ancora.", ORA - 200, "Nicola")
    g.giro(ORA + 200)
    m2 = [r for r in misure_guardia(cfg) if r.get("esito") == "giudicato"][-1]
    verifica("la stessa categoria entro 24 ore → nessun avviso nuovo (ripetuto)",
             m2.get("avviso") == "ripetuto" and len(hub.schede) == 1, str(m2))
    riga(st, 1, "Non voglio più mangiare, mi vedo grassa.", ORA + 300, "Nicola")
    g.giro(ORA + 700)
    m3 = [r for r in misure_guardia(cfg) if r.get("esito") == "giudicato"][-1]
    verifica("un'altra categoria oltre stanza_guardia_avvisi_giorno → tetto, nessun avviso",
             m3.get("avviso") == "tetto" and len(hub.schede) == 1, str(m3))
    # Dopo un riavvio il tetto e la categoria si riprendono dalle misure
    g_b = guardia(cfg, st, avvisi=av)
    verifica("dopo un riavvio: avvisi di oggi e categoria ripresi dal file delle misure",
             len(g_b._avvisi_dati.get("nicola-id", [])) == 1
             and ("nicola-id", "abuso") in g_b._categoria)
    # Due dubbi in giorni diversi entro 7 giorni → un avviso non urgente
    fin = AvvisiFinti()
    cfg5 = cfg_base(registro="r4b", stanza_guardia="attiva")
    st5 = stanza_nuova(cfg5)
    st5._sentita("nicola-id", "Nicola", 1, ORA - 1000)
    g5 = guardia(cfg5, st5, avvisi=fin)
    g5._dubbi[("nicola-id", "autolesionismo")] = [datetime.date.today()
                                                  - datetime.timedelta(days=3)]
    riga(st5, 1, "A volte vorrei sparire.", ORA - 900, "Nicola")
    g5.giro(ORA)
    verifica("due dubbi in giorni diversi della stessa categoria → un avviso non urgente",
             len(fin.mandati) == 1 and fin.mandati[0][3] is False
             and "sparire" not in fin.mandati[0][2] and "Da tenere d'occhio" in fin.mandati[0][2],
             str(fin.mandati))
    riga(st5, 1, "Voglio sparire.", ORA - 100, "Nicola")
    g5.giro(ORA + 500)
    verifica("contrario: il terzo dubbio della settimana non ripete l'avviso",
             len(fin.mandati) == 1)
    fin2 = AvvisiFinti()
    cfg6 = cfg_base(registro="r4c", stanza_guardia="attiva")
    st6 = stanza_nuova(cfg6)
    st6._sentita("nicola-id", "Nicola", 1, ORA - 1000)
    g6 = guardia(cfg6, st6, avvisi=fin2)
    riga(st6, 1, "A volte vorrei sparire.", ORA - 900, "Nicola")
    g6.giro(ORA)
    verifica("contrario: un dubbio solo (nessun altro giorno) → nessun avviso", not fin2.mandati)
    av.close()
    for s in (st, st5, st6):
        s.chiudi()


# ─────────────────────────── 5. pausa e dimentica ───────────────────────────
def prova_pausa_dimentica():
    cfg = cfg_base(registro="r5")
    st = stanza_nuova(cfg)
    st._sentita("nicola-id", "Nicola", 1, ORA - 1000)
    riga(st, 1, "Il mister mi picchia quando sbaglio.", ORA - 900, "Nicola")
    g = guardia(cfg, st)
    st.pausa(1, "ospiti", 240)
    g.giro(ORA)
    verifica("contrario: in pausa (ospiti) → niente raccolta né giudizi",
             not g.giudice.visti and g.in_coda() == 0)
    st.riprendi(1)
    g.raccogli(ORA)
    st.pausa(1, "ospiti", 240)
    verifica("un blocco di prima della pausa aspetta la ripresa",
             g.giro(ORA) == 0 and g.in_coda() == 1 and not g.giudice.visti)
    st.riprendi(1)
    verifica("alla ripresa si giudica", g.giro(ORA) == 1 and len(g.giudice.visti) == 1)
    # «Dimentica» con un blocco in coda: buttato senza giudizio
    cfg2 = cfg_base(registro="r5b")
    st2 = stanza_nuova(cfg2)
    st2._sentita("nicola-id", "Nicola", 1, ORA - 1000)
    riga(st2, 1, "Il mister mi picchia quando sbaglio.", ORA - 900, "Nicola")
    g2 = guardia(cfg2, st2)
    g2.raccogli(ORA)
    st2.dimentica(1)
    g2.giro(ORA)
    es = [r.get("esito") for r in misure_guardia(cfg2)]
    verifica("contrario: «dimentica» → il blocco in coda si butta, nessun giudizio",
             not g2.giudice.visti and es == ["dimenticato"], str(es))
    # «Dimentica» durante il giudizio: il giudizio si butta (nessun avviso)
    cfg3 = cfg_base(registro="r5c", stanza_guardia="attiva")
    st3 = stanza_nuova(cfg3)
    st3._sentita("nicola-id", "Nicola", 1, ORA - 1000)
    riga(st3, 1, "Il mister mi picchia quando sbaglio.", ORA - 900, "Nicola")
    fin = AvvisiFinti()
    g3 = guardia(cfg3, st3, giudice=Giudice(durante=lambda: st3.dimentica(1)), avvisi=fin)
    g3.giro(ORA)
    es = [r.get("esito") for r in misure_guardia(cfg3)]
    verifica("contrario: «dimentica» a metà giudizio → giudizio buttato, nessun avviso",
             es == ["dimenticato"] and not fin.mandati, str(es))
    riga(st3, 1, "Andiamo a cena?", ORA - 800, "Carlo")
    g3.giudice.durante = None
    g3.giro(ORA)
    verifica("dopo «dimentica» le righe nuove si raccolgono di nuovo",
             len(g3.giudice.visti) == 2)
    for s in (st, st2, st3):
        s.chiudi()


# ─────────────────────────── 6. il giudice vero (HTTP finto) ───────────────────────────
class Risposta:
    def __init__(self, testo, codice=200):
        self.status_code, self._t = codice, testo

    def json(self):
        return {"message": {"content": self._t}}


class Client:
    def __init__(self, testo):
        self.testo, self.corpi = testo, []

    def post(self, url, json=None, timeout=None):
        self.corpi.append((url, json, timeout))
        return Risposta(self.testo)


def prova_giudice_modello():
    cfg = cfg_base(registro="r6")
    cfg.llm_model = "gemma4:26b"
    cli = Client('{"livello": "ACUTO", "categoria": "abuso", "contesto": "serio", "righe": [1]}')
    gd = Guardiano(cfg, cliente=cli, log=lambda m: None)
    giud = gm.GiudiceModello(gd, timeout_s=30)
    st = stanza_nuova(cfg)
    st._sentita("nicola-id", "Nicola", 1, ORA - 1000)
    for k in range(30):        # righe lunghe: il prompt resta nella finestra
        riga(st, 1, "Parliamo della partita di ieri " + "e poi ancora " * 40, ORA - 2000 + k,
             "Carlo")
    riga(st, 1, "Il mister mi picchia quando sbaglio.", ORA - 900, "Nicola")
    g = guardia(cfg, st, giudice=giud)
    g.giro(ORA)
    url, corpo, timeout = cli.corpi[-1] if cli.corpi else ("", {}, None)
    verifica("il giudice vero: rilevatore (gemma4:e4b-it-qat), /api/chat, think false, "
             "temperature 0, format con lo schema, timeout della guardia",
             corpo.get("model") == cfg.guardiano_pericolo_modello and url.endswith("/api/chat")
             and corpo.get("think") is False and corpo["options"]["temperature"] == 0
             and corpo.get("format") == gm.SCHEMA and timeout == 30, str(corpo)[:300])
    verifica("stesse opzioni del rilevatore (num_ctx 2048, keep_alive): niente ricaricamenti",
             corpo["options"]["num_ctx"] == cfg.guardiano_num_ctx
             and corpo["keep_alive"] == cfg.guardiano_keep_alive)
    contenuto = corpo["messages"][0]["content"]
    verifica(f"il prompt sta nella finestra (≤ {gm.TESTO_MAX_CAR} caratteri di righe, "
             "le righe da giudicare sempre dentro)",
             len(contenuto) <= len(gm.PROMPT) + gm.TESTO_MAX_CAR + 50
             and "[1] Nicola (minore): Il mister mi picchia" in contenuto, str(len(contenuto)))
    m = [r for r in misure_guardia(cfg) if r.get("esito") == "giudicato"]
    verifica("l'esito del modello letto: acuto", m and m[-1].get("livello") == "acuto")
    cli.testo = "non è JSON"
    js, ms = gd.chiedi_json("x", gm.SCHEMA)
    verifica("contrario: risposta non JSON → None (guasto)", js is None)
    verifica("il guasto non tocca lo stato del guardiano in diretta",
             gd.ultimo_errore_pericolo is None)
    st.chiudi()


# ─────────────────────────── 7. stato --turni e --guardia ───────────────────────────
def prova_stato():
    cfg = cfg_base(registro="r7")
    st = stanza_nuova(cfg)
    st._sentita("nicola-id", "Nicola", 1, ORA - 5000)
    riga(st, 1, "Il mister mi picchia quando sbaglio.", ORA - 4000, "Nicola")
    riga(st, 1, "Dai che vinciamo, ti ammazzo se perdi!", ORA - 2000, "Nicola")
    riga(st, 1, "Ho finito i compiti di matematica.", ORA - 1000, "Nicola")
    g = guardia(cfg, st)
    g.giro(ORA)
    r = gm.riassunto(misure_mod.leggi(cfg.turn_log_dir))
    verifica("riassunto: 3 blocchi, un acuto, ore di chiacchiera, segnali per ora",
             sum(x["blocchi"] for x in r["giorni"].values()) == 3 and r["acuti"] == 1
             and r["ore"] > 0 and r["per_ora"]["acuto"] is not None, str(r)[:300])
    t = gm.testo(r, "ombra")
    verifica("sezione: acuti da leggere, senza parole né nomi",
             "1 acuti da leggere" in t and "picchia" not in t and "Nicola" not in t, t)
    ident = r["elenco"][0]["id"]
    from calliope import stato
    out = io.StringIO()
    vecchio = os.environ.get("CALLIOPE_TURN_LOG_DIR")
    os.environ["CALLIOPE_TURN_LOG_DIR"] = cfg.turn_log_dir
    try:
        with contextlib.redirect_stdout(out):
            stato.guardia_main(cfg, ["--guardia", "--falso", ident], False)
            stato.guardia_main(cfg, ["--guardia"], False)
            esito_ignoto = stato.guardia_main(cfg, ["--guardia", "--vero", "nessuno"], False)
    finally:
        if vecchio is None:
            os.environ.pop("CALLIOPE_TURN_LOG_DIR", None)
        else:
            os.environ["CALLIOPE_TURN_LOG_DIR"] = vecchio
    testo_out = out.getvalue()
    r2 = gm.riassunto(misure_mod.leggi(cfg.turn_log_dir))
    verifica("--falso segna il segnale: acuti letti 1, falsi 1, a settimana 1",
             r2["acuti_letti"] == 1 and r2["acuti_falsi"] == 1 and r2["falsi_settimana"] == 1.0,
             str({k: r2[k] for k in ("acuti_letti", "acuti_falsi", "falsi_settimana")}))
    verifica("--guardia: l'elenco con id, ora, stanza, livello e categoria, letto: falso; "
             "mai le parole", ident in testo_out and "acuto abuso" in testo_out
             and "letto: falso" in testo_out and "picchia" not in testo_out, testo_out)
    verifica("contrario: un id che non c'è → errore", esito_ignoto == 1)
    verifica("con un acuto falso a settimana la sezione dice di non accendere",
             "non accendere" in gm.testo(r2, "ombra"))
    verifica("contrario: nessuna misura → «nessuna misura»",
             "nessuna misura" in gm.testo(gm.riassunto([]), "spenta"))
    verifica("mai le parole delle righe nel file delle misure",
             not any(w in file_misure(cfg) for w in ("picchia", "ammazzo", "matematica")))
    st.chiudi()


def prova_formatta():
    righe = [{"seq": i, "t": ORA, "inizio": ORA + i, "fine": ORA + i + 1, "chi": "persona:x",
              "nome": "Carlo", "sicurezza": "voce", "testo": f"riga {i} " + "parola " * 100}
             for i in range(20)]
    giud = [dict(righe[15], minore=True, nome="Nicola", testo="Il mister mi picchia.")]
    tutte = righe[:15] + giud + righe[16:]
    b = gm.Blocco(1, "satellite cucina", "cucina", tutte, giud, {})
    t = gm.formatta(b)
    verifica("formatta: entro il tetto togliendo prima il contesto più lontano prima del blocco",
             len(t) <= gm.TESTO_MAX_CAR and "[1] Nicola (minore): Il mister mi picchia." in t
             and "riga 0 " not in t and "riga 14 " in t and "riga 19 " in t, str(len(t)))
    verifica("formatta: le righe lunghe accorciate", all(len(x) <= gm.RIGA_MAX_CAR + 30
                                                         for x in t.splitlines()))


# ─────────────────────────── 8. ripresa dal disco dopo un riavvio ───────────────────────────
def _tenuta(path):
    from calliope.stanza.tenuta import Tenuta
    return Tenuta(path, 60, registry=Voci(), log=lambda m: None, avvia=False)


def _avvio(cfg, path):
    """Un «processo»: la stanza con la tenuta su `path` (un avvio nuovo a ogni chiamata)."""
    st = stanza_nuova(cfg)
    st.tenuta = _tenuta(path)
    return st


def _testi(giud) -> list:
    return [r.get("testo") for b in giud.visti for r in b.giudicate]


def prova_ripresa():
    cfg = cfg_base(registro="r8", stanza_tenuta=True)
    path = os.path.join(CARTELLA, "stanza-r8.db")
    # Primo avvio: il diario c'è da 100 ore (le righe di prima del diario non si riprendono)
    st = _avvio(cfg, path)
    t = st.tenuta
    verifica("il diario della guardia si prepara con la tenuta (modulo a sé nello stesso file)",
             t.guardia_dal is not None)
    t.db.execute("UPDATE guardia_meta SET valore = ? WHERE chiave = 'dal'", (ORA - 100 * 3600,))
    t.guardia_dal = ORA - 100 * 3600
    # Due righe giudicate prima del riavvio (una di 30 ore fa): il diario le segna
    riga(st, 1, "Ieri sera il mister mi picchia ancora, uffa.", ORA - 30 * 3600, "Nicola")
    riga(st, 1, "Il mister mi picchia quando sbaglio.", ORA - 5000, "Nicola")
    g = guardia(cfg, st)
    g._ripresa = False                     # il primo avvio non ha niente di prima
    g.giro(ORA - 4000)
    giudicate_prima = _testi(g.giudice)
    # Poi altre righe che non fanno in tempo a essere giudicate prima del riavvio
    st._sentita("nicola-id", "Nicola", 1, ORA - 3005)
    riga(st, 1, "Non voglio più mangiare, mi vedo grassa.", ORA - 3000, "Nicola")
    riga(st, 1, "Andiamo a cena, dai.", ORA - 2990, "Carlo")
    st._sentita("nicola-id", "Nicola", 2, ORA - 2800)
    riga(st, 2, "Sparisco per sempre e nessuno mi trova.", ORA - 2700, "Nicola")
    st.dimentica(2)                        # «dimentica» in sala: via anche dal disco
    g.raccogli(ORA - 2500)                 # in coda, mai giudicate: il processo si ferma
    verifica("prima del riavvio: righe giudicate e una in coda",
             len(giudicate_prima) == 2 and g.in_coda() == 1, f"{giudicate_prima} {g.in_coda()}")
    st.chiudi()
    # Secondo avvio: stessa cartella, avvio nuovo
    st2 = _avvio(cfg, path)
    verifica("un riavvio è un avvio nuovo della tenuta", st2.tenuta.avvio != t.avvio)
    g2 = guardia(cfg, st2)
    n = g2.giro(ORA)
    testi = _testi(g2.giudice)
    verifica("dopo il riavvio: ripresa dal disco solo la riga in coda (la cena di un adulto "
             "con il minore presente compresa), non le giudicate",
             testi == ["Non voglio più mangiare, mi vedo grassa.", "Andiamo a cena, dai."]
             and n == 1, f"n={n} {testi}")
    b = g2.giudice.visti[0] if g2.giudice.visti else None
    verifica("il blocco ripreso è del disco, col nome del satellite e la stanza",
             b is not None and b.disco and b.stanza_nome == "cucina")
    verifica("contrario: la riga dimenticata (sala) non si riprende",
             not any("Sparisco" in x for x in testi))
    verifica("contrario: la riga di 30 ore fa, già giudicata, non si riprende",
             not any("Ieri sera" in x for x in testi))
    mis = misure_guardia(cfg)
    rip = [r for r in mis if r.get("esito") == "ripresa"]
    gd = [r for r in mis if r.get("esito") == "giudicato" and r.get("disco")]
    verifica("misura della ripresa: blocchi, righe e quelle di un minore oltre il limite "
             "(contate, non giudicate)",
             rip and rip[-1].get("blocchi") == 1 and rip[-1].get("righe") == 2
             and rip[-1].get("oltre_limite") == 0 and gd and gd[-1].get("livello") == "acuto",
             str(rip[-1:]))
    verifica("nel diario solo avvio, satellite, seq, esito e istante (mai parole)",
             [c[1] for c in st2.tenuta.db.execute("PRAGMA table_info(guardia_giudicate)")]
             == ["avvio", "sat", "seq", "esito", "t"])
    st2.chiudi()
    # Terzo avvio: niente da riprendere (già giudicate)
    st3 = _avvio(cfg, path)
    g3 = guardia(cfg, st3)
    verifica("contrario: un altro riavvio non rigiudica niente (già nel diario)",
             g3.giro(ORA + 10) == 0 and not g3.giudice.visti)
    st3.chiudi()
    # La riga oltre il limite contata: una riga di un minore non giudicata di 30 ore fa
    cfg_b = cfg_base(registro="r8b", stanza_tenuta=True)
    path_b = os.path.join(CARTELLA, "stanza-r8b.db")
    st = _avvio(cfg_b, path_b)
    st.tenuta.db.execute("UPDATE guardia_meta SET valore = ? WHERE chiave = 'dal'",
                         (ORA - 100 * 3600,))
    st.tenuta.guardia_dal = ORA - 100 * 3600
    riga(st, 1, "Il mister mi picchia quando sbaglio.", ORA - 30 * 3600, "Nicola")
    riga(st, 1, "Non voglio più mangiare, mi vedo grassa.", ORA - 20 * 3600, "Nicola")
    st.chiudi()
    st = _avvio(cfg_b, path_b)
    g = guardia(cfg_b, st)
    g.giro(ORA)
    rip = [r for r in misure_guardia(cfg_b) if r.get("esito") == "ripresa"]
    verifica("dopo un fermo lungo: ripresa solo entro il limite, la più vecchia contata",
             _testi(g.giudice) == ["Non voglio più mangiare, mi vedo grassa."]
             and rip and rip[-1].get("oltre_limite") == 1, f"{_testi(g.giudice)} {rip}")
    r = gm.riassunto(misure_mod.leggi(cfg_b.turn_log_dir))
    tt = gm.testo(r, "ombra")
    verifica("la sezione di calliope stato dice i ripresi e quelli oltre il limite",
             "ripresi dal disco dopo un riavvio 1" in tt and "oltre il limite della ripresa 1"
             in tt, tt)
    st.chiudi()
    # Contrari: ripresa spenta (0 ore), righe non ancora assestate, satellite in pausa,
    # dimentica dopo la ripresa con il blocco in coda, righe di prima del diario
    for nome_c, ore in (("r8c", 0.0), ("r8d", 24.0)):
        c = cfg_base(registro=nome_c, stanza_tenuta=True, stanza_guardia_ripresa_h=ore)
        pth = os.path.join(CARTELLA, f"stanza-{nome_c}.db")
        st = _avvio(c, pth)
        st.tenuta.db.execute("UPDATE guardia_meta SET valore = ? WHERE chiave = 'dal'",
                             (ORA - 100 * 3600,))
        st.tenuta.guardia_dal = ORA - 100 * 3600
        riga(st, 1, "Il mister mi picchia quando sbaglio.", ORA - 200, "Nicola")
        riga(st, 1, "Non voglio più mangiare, mi vedo grassa.", ORA - 60, "Nicola")
        st.chiudi()
        st = _avvio(c, pth)
        g = guardia(c, st)
        if ore == 0:
            verifica("contrario: stanza_guardia_ripresa_h 0 → niente dal disco",
                     g.giro(ORA) == 0 and not g.giudice.visti)
        else:
            verifica("contrario: righe di prima non ancora assestate → si aspetta",
                     g.giro(ORA) == 0 and g._ripresa)
            st.pausa(1, "ospiti", 60)
            verifica("contrario: il satellite in pausa (ospiti) → non si riprende",
                     g.giro(ORA + 200) == 0 and g._ripresa and not g.giudice.visti)
            st.riprendi(1)
            g.raccogli(ORA + 200)
            verifica("alla ripresa dell'ascolto si riprende", g.in_coda() == 1 and not g._ripresa)
            st.dimentica(1)
            g.giro(ORA + 200)
            es = [r.get("esito") for r in misure_guardia(c)]
            verifica("contrario: «dimentica» col blocco del disco in coda → buttato",
                     not g.giudice.visti and "dimenticato" in es, str(es))
        st.chiudi()
    c = cfg_base(registro="r8e", stanza_tenuta=True)
    pth = os.path.join(CARTELLA, "stanza-r8e.db")
    st = _avvio(c, pth)
    riga(st, 1, "Il mister mi picchia quando sbaglio.", ORA - 3000, "Nicola")
    st.tenuta.db.execute("UPDATE guardia_meta SET valore = ? WHERE chiave = 'dal'", (ORA - 10,))
    st.chiudi()
    st = _avvio(c, pth)
    g = guardia(c, st)
    verifica("contrario: righe di prima del diario (la guardia in memoria le aveva già) → "
             "non si riprendono", g.giro(ORA) == 0 and not g.giudice.visti)
    st.chiudi()
    c = cfg_base(registro="r8f")
    st = stanza_nuova(c)
    g = guardia(c, st)
    g.giro(ORA)
    verifica("contrario: senza la tenuta nessuna ripresa e nessun diario",
             not g._ripresa and st.tenuta is None)
    st.chiudi()


# ─────────────────────────── 9. modalità gioco ───────────────────────────
def prova_gioco():
    cfg = cfg_base(registro="r9")
    st = stanza_nuova(cfg)
    aperto = {1: False, 2: False}
    g = guardia(cfg, st, gioco=lambda sat: aperto.get(sat, False))
    st._sentita("nicola-id", "Nicola", 1, ORA - 3000)
    aperto[1] = True
    g.osserva_giochi(ORA - 2000)
    g.osserva_giochi(ORA - 1500)
    aperto[1] = False
    g.osserva_giochi(ORA - 1490)
    verifica("il periodo di gioco: dall'apertura all'ultima volta aperto",
             g._giochi.get("1") == [(ORA - 2000, ORA - 1500)], str(g._giochi))
    # Durante il gioco: una minaccia di un altro (il modello sbaglia: acuto serio)
    st._sentita("nicola-id", "Nicola", 1, ORA - 1950)
    riga(st, 1, "Ti ammazzo, sei morto!", ORA - 1900, None)
    g.giro(ORA)
    b = g.giudice.visti[-1] if g.giudice.visti else None
    m = [r for r in misure_guardia(cfg) if r.get("esito") == "giudicato"][-1:]
    m = m[0] if m else {}
    verifica("gioco aperto: il prompt dichiara il gioco",
             b is not None and b.gioco and gm.GIOCO.strip() in gm.prompt(b))
    verifica("gioco aperto: la minaccia di un altro (acuto serio dal modello) → dubbio "
             "(gioco_dichiarato), nessun avviso",
             m.get("livello") == "dubbio" and m.get("motivo") == "gioco_dichiarato"
             and m.get("gioco") is True and m.get("avviso") is None, str(m))
    # Durante il gioco: la frase grave detta sul serio dal minore resta acuta
    aperto[1] = True
    g.osserva_giochi(ORA - 1000)
    riga(st, 1, "Basta, non è per il gioco: a volte voglio morire davvero.", ORA - 990,
         "Nicola")
    g.osserva_giochi(ORA - 900)
    g.giro(ORA)
    m = [r for r in misure_guardia(cfg) if r.get("esito") == "giudicato"][-1]
    verifica("gioco aperto: autolesionismo detto sul serio dal minore → resta acuto",
             m.get("livello") == "acuto" and m.get("categoria") == "autolesionismo"
             and m.get("gioco") is True, str(m))
    # Durante il gioco: un acuto non chiaro del minore → dubbio; un dubbio non chiaro → niente
    riga(st, 1, "Mi butto giù dal ponte, tanto ho tre vite.", ORA - 600, "Nicola")
    g.osserva_giochi(ORA - 580)
    g.giro(ORA)
    m = [r for r in misure_guardia(cfg) if r.get("esito") == "giudicato"][-1]
    verifica("gioco aperto: acuto non chiaro → dubbio (gioco_dichiarato)",
             m.get("livello") == "dubbio" and m.get("motivo") == "gioco_dichiarato", str(m))
    riga(st, 1, "Adesso voglio sparire dietro il muro, così non mi trovano.", ORA - 300,
         "Nicola")
    g.osserva_giochi(ORA - 280)
    g.giro(ORA)
    m = [r for r in misure_guardia(cfg) if r.get("esito") == "giudicato"][-1]
    verifica("gioco aperto: dubbio non chiaro → niente (gioco_dichiarato)",
             m.get("livello") == "niente" and m.get("motivo") == "gioco_dichiarato", str(m))
    # Contrari: la stessa minaccia a gioco chiuso è acuta (presente); il gioco di un'altra
    # stanza non conta; senza la funzione dei giochi nessun gioco
    aperto[1] = False
    g.osserva_giochi(ORA - 250)
    st._sentita("nicola-id", "Nicola", 1, ORA - 160)
    riga(st, 1, "Se lo dici alla mamma, sei morto.", ORA - 150, None)
    g.giro(ORA + 200)
    m = [r for r in misure_guardia(cfg) if r.get("esito") == "giudicato"][-1]
    b = g.giudice.visti[-1]
    verifica("contrario: gioco chiuso (oltre il margine) → la minaccia resta acuta (presente) "
             "e il prompt non parla di giochi",
             m.get("livello") == "acuto" and m.get("modo_minore") == "presente"
             and not m.get("gioco") and not b.gioco and "videogioco" not in gm.prompt(b), str(m))
    cfg2 = cfg_base(registro="r9b")
    st2 = stanza_nuova(cfg2)
    st2._sentita("nicola-id", "Nicola", 1, ORA - 3000)
    g2 = guardia(cfg2, st2, gioco=lambda sat: sat == 2)
    g2.osserva_giochi(ORA - 2000)
    g2.osserva_giochi(ORA - 1000)
    st2._sentita("nicola-id", "Nicola", 1, ORA - 1510)
    riga(st2, 1, "Ti ammazzo, sei morto!", ORA - 1500, None)
    g2.giro(ORA)
    m = [r for r in misure_guardia(cfg2) if r.get("esito") == "giudicato"][-1]
    verifica("contrario: il gioco aperto in sala non vale per la cucina → acuto",
             m.get("livello") == "acuto" and not m.get("gioco"), str(m))
    g3 = guardia(cfg_base(registro="r9c"), st2)
    g3.osserva_giochi(ORA)
    verifica("contrario: senza la funzione dei giochi nessun periodo",
             not g3._aperti and not g3._giochi)
    # I periodi di gioco sul diario: dopo un riavvio la riga ripresa sa del gioco
    c = cfg_base(registro="r9d", stanza_tenuta=True)
    pth = os.path.join(CARTELLA, "stanza-r9d.db")
    st = _avvio(c, pth)
    st.tenuta.db.execute("UPDATE guardia_meta SET valore = ? WHERE chiave = 'dal'",
                         (ORA - 100 * 3600,))
    st.tenuta.guardia_dal = ORA - 100 * 3600
    st._sentita("nicola-id", "Nicola", 1, ORA - 3000)
    gioca = [True]
    g = guardia(c, st, gioco=lambda sat: gioca[0] and sat == 1)
    g.osserva_giochi(ORA - 2000)
    st._sentita("nicola-id", "Nicola", 1, ORA - 1910)
    riga(st, 1, "Ti ammazzo, sei morto!", ORA - 1900, "Carlo")
    g.osserva_giochi(ORA - 1800)
    st.chiudi()                            # il riavvio con il gioco ancora aperto
    st = _avvio(c, pth)
    gg = st.tenuta.giochi(0)
    verifica("il periodo di gioco è sul diario (solo satellite e tempi), allungato",
             len(gg) == 1 and gg[0][0] == "1" and abs(gg[0][1] - (ORA - 2000)) < 0.01
             and abs(gg[0][2] - (ORA - 1800)) < 0.01, str(gg))
    g = guardia(c, st)
    g.giro(ORA)
    m = [r for r in misure_guardia(c) if r.get("esito") == "giudicato"][-1:]
    m = m[0] if m else {}
    verifica("dopo il riavvio la riga ripresa dal disco si giudica col gioco dichiarato",
             m.get("disco") is True and m.get("gioco") is True
             and m.get("livello") == "dubbio", str(m))
    st.chiudi()
    for s in (st2,):
        s.chiudi()


def prova_giochi_in_corso():
    from types import SimpleNamespace
    from calliope.schermi.giochi import Giochi, Partita, Posto, VIVO_S
    gi = Giochi(Config(), hub=None)
    mitt = SimpleNamespace(persona="nicola-id", nome="Nicola", livello="familiare")
    p = Partita("labirinto", 1, {"titolo": "Labirinto", "scheda": {}}, mitt)
    posto = Posto(5, mitt, True)
    p.posti[5] = posto
    gi.partite[p.id] = p
    verifica("contrario: riquadro non ancora pronto → nessun gioco in corso",
             not gi.in_corso([5]))
    posto.aperto, posto.contatto = True, time.time()
    verifica("riquadro aperto e vivo sullo schermo → gioco in corso", gi.in_corso([5]))
    verifica("contrario: un altro schermo → no; nessuno schermo → no",
             not gi.in_corso([6]) and not gi.in_corso([]))
    posto.contatto = time.time() - VIVO_S - 5
    verifica("contrario: la pagina tace da oltre VIVO_S → no", not gi.in_corso([5]))
    posto.contatto, posto.fermato = time.time(), True
    verifica("contrario: fermato (tempo dei giochi finito) → no", not gi.in_corso([5]))
    posto.fermato, posto.aperto = False, False
    verifica("contrario: chiuso («chiuso», ✕) → no", not gi.in_corso([5]))


# ─────────────────────────── 10. schemi di stanza.db delle versioni di prima ───────────────────
def prova_schemi():
    """stanza.db scritto da ciascuna versione di prima si apre con questa: la tenuta del 14/10
    (stanza_tenuta 1), il ramo della guardia (stanza_tenuta 1 + stanza_guardia 1), i conoscenti
    (stanza_tenuta 2, colonna `nota`). Le righe di prima restano e la ripresa le legge."""
    import sqlite3
    from calliope.persistenza import versione_schema
    from calliope.stanza import tenuta as tm

    def crea(nome, tenuta_v, guardia_v):
        pth = os.path.join(CARTELLA, f"schema-{nome}.db")
        db = sqlite3.connect(pth)
        tm._v1(db)
        if tenuta_v >= 2:
            tm._v2(db)
        if guardia_v >= 1:
            tm._g1(db)
            db.execute("UPDATE guardia_meta SET valore = ? WHERE chiave = 'dal'",
                       (ORA - 100 * 3600,))
        db.execute("CREATE TABLE IF NOT EXISTS meta_schema (modulo TEXT PRIMARY KEY, "
                   "versione INTEGER NOT NULL)")
        db.execute("INSERT INTO meta_schema VALUES (?, ?)", (tm.MODULO, tenuta_v))
        if guardia_v:
            db.execute("INSERT INTO meta_schema VALUES (?, ?)", (tm.MODULO_GUARDIA, guardia_v))
        db.execute("INSERT INTO righe(avvio, sat, stanza, satellite, seq, inizio, fine, testo, "
                   "chi, persona, nome, sicurezza, minore) VALUES ('vecchio', '1', 'cucina', "
                   "'satellite cucina', 1, ?, ?, 'Il mister mi picchia quando sbaglio.', "
                   "'persona:nicola-id', 'nicola-id', 'Nicola', 'voce', 1)",
                   (ORA - 3003, ORA - 3000))
        db.commit()
        db.close()
        return pth

    for nome, tv, gv in (("tenuta-1", 1, 0), ("guardia", 1, 1), ("conoscenti", 2, 0)):
        pth = crea(nome, tv, gv)
        t = tm.Tenuta(pth, 60, registry=Voci(), log=lambda m: None, avvia=False)
        colonne = [c[1] for c in t.db.execute("PRAGMA table_info(righe)")]
        ok = (t.scrivibile and versione_schema(t.db, tm.MODULO) == len(tm.MIGRAZIONI)
              and versione_schema(t.db, tm.MODULO_GUARDIA) == len(tm.MIGRAZIONI_GUARDIA)
              and "nota" in colonne and t.guardia_dal is not None)
        if gv == 0:
            # Il diario nasce adesso: per leggere la riga di prima si sposta indietro `dal`
            t.db.execute("UPDATE guardia_meta SET valore = ? WHERE chiave = 'dal'",
                         (ORA - 100 * 3600,))
            t.guardia_dal = ORA - 100 * 3600
        righe = t.righe_guardia(ORA - 24 * 3600)
        verifica(f"stanza.db della versione «{nome}» (stanza_tenuta {tv}, stanza_guardia {gv}) "
                 "si apre: schemi all'ultima versione, `nota` e diario, la riga di prima letta",
                 ok and len(righe) == 1 and righe[0]["nota"] is None
                 and righe[0]["_giudicata"] is False,
                 f"{colonne} {righe}")
        t.chiudi()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    for f in (prova_spenta, prova_righe, prova_carico, prova_filtri, prova_attiva,
              prova_pausa_dimentica, prova_giudice_modello, prova_stato, prova_formatta,
              prova_ripresa, prova_gioco, prova_giochi_in_corso, prova_schemi):
        print(f"── {f.__name__}", flush=True)
        try:
            f()
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            verifica(f"{f.__name__} senza eccezioni", False, f"{type(e).__name__}: {e}")
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}", flush=True)
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
