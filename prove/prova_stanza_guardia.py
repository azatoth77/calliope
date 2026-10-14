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
- `calliope stato --turni` (sezione) e `calliope stato --guardia` (elenco, --falso/--vero).

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

    REGOLE = (("mi picchia", "ACUTO", "abuso", "serio"),
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

    def solo_schermo(self, minore, tipo, testo, urgente=False, registry=None):
        self.mandati.append((minore.id, tipo, testo, urgente))
        return 1


def guardia(cfg, st, giudice=None, avvisi=None, occupato=()):
    return gm.Guardia(cfg, st, giudice or Giudice(), avvisi=avvisi, occupato=occupato,
                      log=LOG.append, avvia=False)


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


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    for f in (prova_spenta, prova_righe, prova_carico, prova_filtri, prova_attiva,
              prova_pausa_dimentica, prova_giudice_modello, prova_stato, prova_formatta):
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
