import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco delle frasi pronte meno monotone (12/10, calliope/frasi.py; fasi 0 e 1 di
docs/ricerche/2026-10-08-frasi-pronte.md, roadmap V3).

Catalogo: stessi segnaposto in ogni variante, la forma breve con i fatti fissi, la domanda in
fondo identica («Procedo?»), la stessa punteggiatura finale della frase di oggi, niente «tu» nel
formale, niente «!» nel computer di bordo, nessuna dichiarazione d'azione nuova, classi bloccate
(sfida, permessi, politica, ripieghi, annunci) senza varianti. Scelta: «ombra» dice la frase di
oggi (le prove che leggono i testi esatti non cambiano) e scrive la variante; «attivo» la dice;
«spento» solo l'id; rotazione per persona senza le ultime due, forma breve solo dopo una volta
detta e nei turni giusti, tono di chi parla o della casa. Uscita unica: l'id passa da lì, una
volta per scelta, anche a pezzi; il ciclo lo scrive nel registro (una volta per id, regola
`frase_breve`); sotto i 100 µs per frase. Misura: ripetizioni ogni 100 per pronte e modello,
stessa persona e giorno, finestra di 20, senza parole per id, stima delle varianti in ombra;
contrari. Campione di 30 per chi amministra. Cortesia: in ombra come prima, attiva per persona.
"""

import collections
import tempfile
import time
import types
from pathlib import Path

from calliope import frasi as F
from calliope.brain import ACTION_CLAIM
from calliope.config import TONI, VALIDATORI, Config
from calliope.cortesia import RISPOSTE, Cortesia
from calliope.eventi.uscita import Uscita

errori = 0


def verifica(nome, ottenuto, atteso):
    global errori
    ok = ottenuto == atteso
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome} → {ottenuto!r}" + ("" if ok else f"  (atteso {atteso!r})"))


# ── catalogo ──
verifica("i toni del catalogo sono quelli di config.TONI", set(F.TONI_FRASI), set(TONI))
TU = {"ti", "te", "tu", "tuo", "tua", "tuoi", "tue", "puoi", "vuoi", "hai", "sei", "devi",
      "chiedimi", "chiedimela", "chiedi", "dimmi", "provala", "fai", "figurati"}
problemi = []
for v in F.CATALOGO.values():
    tutte = [(t, b, f) for t in F.TONI_FRASI for b in (False, True) for f in v.forme(t, b)]
    if v.bloccata:
        if v.toni or v.breve:
            problemi.append(f"{v.id}: classe bloccata con varianti")
        continue
    base = v.base
    sp = F.segnaposto(base) if base else set()
    for t, breve, f in tutte:
        s = F.segnaposto(f)
        if base and not breve and s != sp:
            problemi.append(f"{v.id}/{t}: segnaposto {s} invece di {sp}")
        if breve and not (set(v.fissi) <= s <= sp):
            problemi.append(f"{v.id}/{t} breve: segnaposto {s} (fissi {v.fissi})")
        if v.domanda and not f.endswith(v.domanda):
            problemi.append(f"{v.id}/{t}: la domanda in fondo non è «{v.domanda}»: {f}")
        if not v.domanda and "?" in f:
            problemi.append(f"{v.id}/{t}: una domanda che la frase di oggi non fa: {f}")
        if base and f[-1] != base[-1] and not (f[-1] in ".!" and base[-1] in ".!"):
            problemi.append(f"{v.id}/{t}: finisce con {f[-1]!r}, la base con {base[-1]!r}")
        parole = {w.lower() for w in F.re.findall(r"[^\W\d_]+", f)}
        if t == "formale" and parole & TU:
            problemi.append(f"{v.id}/formale: forme del tu {sorted(parole & TU)}: {f}")
        if t == "computer_di_bordo" and "!" in f:
            problemi.append(f"{v.id}/computer_di_bordo: «!»: {f}")
        es = f.format(**v.esempio) if s else f
        es_base = base.format(**v.esempio) if base else ""
        if ACTION_CLAIM.search(es) and not ACTION_CLAIM.search(es_base):
            problemi.append(f"{v.id}/{t}: dichiara un'azione: {es}")
        if F.re.match(r"\s*(fatto|eseguito)\b", f, F.re.I) and not (
                base and F.re.match(r"\s*fatto\b", base, F.re.I)):
            problemi.append(f"{v.id}/{t}: comincia con «Fatto»: {f}")
    if base and v.toni and base not in v.toni.get("normale", ()):
        problemi.append(f"{v.id}: la base non è fra le varianti del tono normale")
    for t in F.TONI_FRASI:
        if not v.forme(t):
            problemi.append(f"{v.id}/{t}: nessuna forma")
verifica("catalogo: segnaposto, domanda, registro, «!», azioni, Fatto (nessun problema)",
         problemi, [])
cortesia_n = {(f, t): len(F.CATALOGO[f"cortesia.{f}"].forme(t)) for f in ("grazie", "conferma")
              for t in ("normale", "formale", "amichevole", "ironico")}
verifica("cortesia: almeno 6 frasi per i toni pieni", min(cortesia_n.values()) >= 6, True)
verifica("cortesia: le frasi di oggi sono tutte nel catalogo",
         all(set(RISPOSTE[t][f]) <= set(F.CATALOGO[f"cortesia.{f}"].forme(t))
             for t in RISPOSTE for f in RISPOSTE[t]), True)

# ── lingua (12/10 sera, dal campione riletto da chi amministra) ──
# Accordo col titolo: il nome lo sceglie chi scrive l'estensione («il convertitore di misure»),
# quindi «è attiva» e «usarla» vanno col nome comune davanti, e mai una preposizione attaccata a
# «{titolo}» («Quanto a «il convertitore»», «Sviluppo di «il convertitore»»)
_PREP = F.re.compile(r"\b(?:di|a|ad|da|in|su|quanto a)\s+«\{titolo\}»", F.re.I)
_ACCORDO = F.re.compile(r"(?<!estensione )«\{titolo\}»\s+(?:è\s+)?(?:ora\s+)?attiv[ao]")
_SUPPONE = F.re.compile(r"\b(?:ancora|di nuovo|sempre)\b", F.re.I)


def parole(s):
    return {w.lower() for w in F.re.findall(r"[^\W\d_]+", s)}


def lingua(ident, tono, breve, f):
    """I difetti di lingua di una forma (lista vuota: va bene)."""
    out = []
    if _PREP.search(f):
        out.append("preposizione davanti al titolo")
    if _ACCORDO.search(f):
        out.append("accordo col titolo")
    # La forma breve si dice alla prima ripetizione, con qualunque cosa sia successa nel
    # frattempo: niente «ancora», «di nuovo», «sempre» che danno per scontato che nulla sia cambiato
    if breve and _SUPPONE.search(f):
        out.append("la forma breve suppone che nulla sia cambiato")
    if ident == "lavori.proposta":
        carico = f.format(cosa="X", agente="sulla DGX", coda="", stima="S", dopo="",
                          carico="; prima devo caricare il modello, ci vuole un minuto in più")
        if F.re.search(r"in più,\s+che\b", carico):
            out.append("inciso staccato dall'agente dopo {carico}")
    return out


# Le classi bloccate no: il testo è quello del codice, qui solo per la misura
difetti = [(v.id, t, b, f, lingua(v.id, t, b, f)) for v in F.CATALOGO.values() if not v.bloccata
           for t in F.TONI_FRASI for b in (False, True) for f in v.forme(t, b)
           if lingua(v.id, t, b, f)]
verifica("lingua: accordo, preposizioni, forme brevi, incisi (nessun problema)", difetti, [])
verifica("contrari: i difetti del campione del 12/10 si vedono", [lingua(*x) for x in (
    ("estensione.attiva", "formale", False, "Fatto: «{titolo}» è ora attiva, versione {versione}."),
    ("sviluppo.stato", "formale", False, "Quanto a «{titolo}», {dove}."),
    ("sviluppo.stato", "normale", False, "Sviluppo di «{titolo}»: {dove}."),
    ("lavori.nessuno", "normale", True, "Ancora nessun lavoro in corso."),
    ("lavori.proposta", "ironico", False, "{cosa}: lo affido all'agente {agente}{coda}{carico}, "
     "che ha più pazienza di me. {stima}.{dopo} Procedo?"))],
    [["accordo col titolo"], ["preposizione davanti al titolo"],
     ["preposizione davanti al titolo"], ["la forma breve suppone che nulla sia cambiato"],
     ["inciso staccato dall'agente dopo {carico}"]])
verifica("contrari: forme giuste non segnalate", [lingua(*x) for x in (
    ("estensione.attiva", "normale", False, "Fatto: l'estensione «{titolo}» è attiva."),
    ("lavori.in_coda", "normale", True, "In coda dopo «{titolo}», ti avviso."),
    ("lavori.nessuno", "normale", True, "Nessun lavoro in corso."))], [[], [], []])

# La stima e l'approvazione entrano in ogni tono: mai il «tu» (né il «lei») nei valori
from calliope.agenti.servizio import APPROVAZIONE, STIME  # noqa: E402
LEI = {"lei", "può", "sua", "suo", "desidera"}
verifica("proposta: stima e approvazione senza «tu» né «lei» (valgono per ogni tono)",
         [x for x in list(STIME.values()) + [APPROVAZIONE] if parole(x) & (TU | LEI)], [])
verifica("contrario: la stima di prima («te la faccio approvare») si vede",
         sorted(parole("Ci vorranno alcuni minuti, poi te la faccio approvare") & (TU | LEI)),
         ["te"])
fo = F.Frasi("attivo", breve_turni=3)
fo.inizio_turno("anna", "formale")
pe = dict(cosa="È una funzione nuova di Calliope", agente="sulla DGX", coda="", carico="",
          stima=STIME["estensione"], dopo=APPROVAZIONE)
p1 = fo.scegli("lavori.proposta", **pe)
fo.detta(p1)
fo.inizio_turno("anna", "formale")
p2 = fo.scegli("lavori.proposta", **pe)
verifica("proposta di un'estensione nel formale: niente «tu», l'approvazione detta, anche breve",
         [(sorted(parole(x) & TU), "andrà approvata" in x, x.endswith("Procedo?"), x != p1 or k == 0)
          for k, x in enumerate((p1, p2))],
         [([], True, True, True), ([], True, True, True)])

verifica("contrario: sfida, permessi, politica, ripieghi senza varianti",
         sorted({v.classe for v in F.CATALOGO.values() if v.bloccata}),
         ["annuncio", "permesso", "politica", "ripiego", "sfida"])

# La base è la frase di oggi, parola per parola (le prove che leggono i testi esatti)
OGGI = {
    ("lavori.avviato", ()): "Ci lavoro in secondo piano: ti avviso quando è pronto. Intanto "
                            "puoi chiedermi altro.",
    ("lavori.in_coda", (("titolo", "Relazione"),)):
        "D'accordo: lo metto in coda dopo «Relazione». Ti avviso quando è pronto.",
    ("lavori.proposta", (("cosa", "È un lavoro di programmazione"), ("agente", "sulla DGX"),
                         ("coda", ""), ("carico", ""), ("stima", "Ci vorranno alcuni minuti"),
                         ("dopo", ""))):
        "È un lavoro di programmazione: lo affido all'agente sulla DGX. Ci vorranno alcuni "
        "minuti e ti avviso quando ha finito. Procedo?",
    ("lavori.nessuno", ()): "Non ho lavori in corso.",
    ("lavori.nessuna_domanda", ()): "Non ho lavori che aspettano una risposta.",
    ("estensione.attiva", (("titolo", "Meteo"), ("versione", 3), ("cosa", ": dice il meteo"))):
        "Fatto: l'estensione «Meteo» è attiva, versione 3: dice il meteo. Da adesso puoi usarla.",
    ("sviluppo.correzione", (("caso", " con «venti»"),)):
        "D'accordo: lo faccio correggere a chi l'ha scritto. Ci lavora in secondo piano; quando "
        "è pronto rifacciamo la prova con «venti».",
    ("sviluppo.stato", (("titolo", "Meteo"), ("dove", "siamo al collaudo (3 di 5)"))):
        "Stiamo sviluppando «Meteo»: siamo al collaudo (3 di 5).",
}
for modo in ("ombra", "spento"):
    fr = F.Frasi(modo)
    fr.inizio_turno("p1", "ironico")
    verifica(f"{modo}: la frase di oggi, parola per parola, anche nel tono ironico",
             [fr.scegli(i, **dict(val)) for (i, val) in OGGI], list(OGGI.values()))

# ── scelta ──
fr = F.Frasi("ombra", breve_turni=6)
fr.inizio_turno("anna", "formale")
t = fr.scegli("lavori.avviato")
d = fr.detta(t)
verifica("ombra: detta la base", t, OGGI[("lavori.avviato", ())])
verifica("ombra: nel registro la variante che avrebbe scelto, senza parole",
         (d[0]["id"], d[0]["tono"], sorted(d[0]["ombra"]), "variante" in d[0]),
         ("lavori.avviato", "formale", ["breve", "uguale", "variante"], False))
fr.inizio_turno("anna", "formale")
d = fr.detta(fr.scegli("lavori.avviato"))
verifica("ombra: la seconda volta la forma breve (solo in ombra)", d[0]["ombra"]["breve"], True)
fs = F.Frasi("spento")
fs.inizio_turno("anna", "formale")
verifica("spento: solo l'id", fs.detta(fs.scegli("lavori.avviato")), [{"id": "lavori.avviato"}])

fa = F.Frasi("attivo", breve_turni=0)
fa.inizio_turno("anna", "normale")
dette = []
for _ in range(6):
    fa.inizio_turno("anna", "normale")
    x = fa.scegli("lavori.avviato")
    fa.detta(x)
    dette.append(x)
forme = F.CATALOGO["lavori.avviato"].forme("normale")
verifica("attivo: rotazione per persona sulle 3 varianti", dette, list(forme) * 2)
verifica("attivo: mai una delle ultime due", all(dette[i] not in dette[i - 2:i]
                                                for i in range(2, len(dette))), True)
fa.inizio_turno("bruno", "normale")
verifica("attivo: un'altra persona riparte dalla sua rotazione", fa.scegli("lavori.avviato"),
         forme[0])
# Non detta → non conta per la rotazione
fa2 = F.Frasi("attivo", breve_turni=0)
fa2.inizio_turno("carla", "normale")
a, b = fa2.scegli("lavori.avviato"), fa2.scegli("lavori.avviato")
verifica("contrario: una scelta non detta non fa girare la rotazione", a == b, True)

fb = F.Frasi("attivo", breve_turni=3)
fb.inizio_turno("anna", "amichevole")
x1 = fb.scegli("lavori.proposta", **dict(OGGI_P := dict(list(OGGI)[2][1])))
fb.detta(x1)
fb.inizio_turno("anna", "amichevole")
x2 = fb.scegli("lavori.proposta", **OGGI_P)
info2 = fb.detta(x2)
verifica("attivo: la prima volta intera, con la stima", "Ci vorranno alcuni minuti" in x1, True)
verifica("attivo: la seconda volta breve, con «Procedo?» in fondo e gli stessi fatti",
         (info2[0]["breve"], x2.endswith("Procedo?"), "sulla DGX" in x2,
          x2.startswith("È un lavoro di programmazione")), (True, True, True, True))
for _ in range(4):
    fb.inizio_turno("anna", "amichevole")
x3 = fb.scegli("lavori.proposta", **OGGI_P)
verifica("contrario: dopo più di frasi_breve_turni turni di nuovo intera",
         fb.detta(x3)[0]["breve"], False)
fb.inizio_turno("anna", "amichevole")
fb._persone["anna"]["ultimo"]["lavori.proposta"] = (fb._persone["anna"]["turno"],
                                                     time.time() - F.BREVE_S - 5)
verifica("contrario: oltre un'ora di nuovo intera",
         fb.detta(fb.scegli("lavori.proposta", **OGGI_P))[0]["breve"], False)
fb.inizio_turno("dario", "amichevole")
verifica("contrario: la forma breve è per persona", fb.detta(fb.scegli(
    "lavori.proposta", **OGGI_P))[0]["breve"], False)
verifica("contrario: un id senza forme brevi non le inventa",
         [fb.detta(fb.scegli("lavori.nessuna_domanda"))[0]["breve"] for _ in range(3)],
         [False, False, False])

ft = F.Frasi("attivo", tono_casa="formale")
verifica("tono: senza un turno, quello della casa (lei)",
         ft.scegli("lavori.avviato") in F.CATALOGO["lavori.avviato"].forme("formale"), True)
ft.inizio_turno("anna", "computer_di_bordo")
verifica("tono: quello di chi parla", ft.scegli("lavori.avviato")
         in F.CATALOGO["lavori.avviato"].forme("computer_di_bordo"), True)
ft.inizio_turno("anna", "inventato")
verifica("contrario: un tono sconosciuto → quello della casa",
         ft.scegli("lavori.nessuno") in F.CATALOGO["lavori.nessuno"].forme("formale"), True)
verifica("contrario: una classe bloccata resta parola per parola anche attiva",
         ft.scegli("politica.non_chiesto", cosa="apra la porta"),
         "Non me l'hai chiesto: vuoi che apra la porta?")

# ── riconoscere ──
verifica("riconosci: politica, sfida, lavori", [F.riconosci(x) for x in (
    "C'è di mezzo una pagina web, quindi chiedo a te: vuoi che apra il file?",
    "Per conferma ripeti: mela rossa.",
    "Non ho lavori in corso. L'ultimo, «Meteo», è finito.")],
    [["politica.conferma"], ["sfida.conferma"], ["lavori.nessuno"]])
verifica("contrario: «Ti avviso quando è pronto.» dentro l'avvio non è la coda",
         F.riconosci(OGGI[("lavori.avviato", ())]), ["lavori.avviato"])
verifica("contrari: risposte del modello", [F.riconosci(x) for x in (
    "Sono le dieci e un quarto.", "Ho acceso la luce in cucina.", "Prego!", "Procedo?", "")],
    [[], [], [], [], []])
verifica("normalizza: numeri e «…» tolti", F.normalizza("Sono le 10:15, «Meteo» è pronto!"),
         "sono le è pronto")

# ── uscita unica ──
class Voce:
    def __init__(self):
        self.dette, self.played, self.interrupted, self.muto = [], [], False, False

    def start_turn(self):
        pass

    def say(self, t):
        self.dette.append(t)

    def say_cached(self, t):
        self.dette.append(t)


F.FRASI.__init__("ombra")
u = Uscita(Voce(), log=lambda m: None)
viste = []
u.su_pronta = viste.append
u.turno()
F.FRASI.inizio_turno("anna", "normale")
testo = F.scegli("lavori.avviato")
pezzi = ["Ci lavoro in secondo piano: ti avviso quando è pronto.", "Intanto puoi chiedermi altro."]
detti = [u.di(p, "risposta", "esito") for p in pezzi]
verifica("uscita: la frase a pezzi conta una volta, col suo id",
         [x["id"] for x in viste], ["lavori.avviato"])
verifica("uscita: l'id nel detto", detti[0].get("pronte", [{}])[0].get("id"), "lavori.avviato")
u.di("Sono le dieci e un quarto.", "risposta")
verifica("contrario: una frase del modello non è pronta", len(viste), 1)
u.di("Non me l'hai chiesto: vuoi che apra la porta?", "risposta", "esito")
verifica("uscita: la politica riconosciuta per modello", viste[-1], {"id": "politica.non_chiesto"})
u.su_pronta = lambda p: 1 / 0
verifica("contrario: un errore della misura non ferma la voce",
         u.di(testo, "risposta")["testo"], testo)
F.FRASI.__init__("ombra")
t0 = time.perf_counter()
for _ in range(500):
    F.FRASI.detta("Sono le dieci e un quarto, e fuori ci sono diciotto gradi con il cielo sereno.")
us = (time.perf_counter() - t0) / 500 * 1e6
verifica(f"latenza: riconoscere una frase sotto i 100 µs ({us:.0f} µs)", us < 100, True)

# ── il ciclo: il registro dei turni ──
from calliope.ciclo import Ciclo  # noqa: E402
regole = []
ns = types.SimpleNamespace(rec={"regole": []}, rule=lambda n: ns.rec["regole"].append(n))
for info in ({"id": "lavori.avviato", "tono": "normale", "variante": 1, "breve": True},
             {"id": "lavori.avviato"}, {"id": "politica.conferma"}):
    Ciclo._pronta_detta(ns, info)
verifica("ciclo: pronte nel turno, una volta per id, e la regola frase_breve",
         ([p["id"] for p in ns.rec["pronte"]], ns.rec["regole"]),
         (["lavori.avviato", "politica.conferma"], ["frase_breve"]))
ns2 = types.SimpleNamespace(rec=None, rule=lambda n: None)
Ciclo._pronta_detta(ns2, {"id": "lavori.avviato"})
verifica("contrario: fuori da un turno non scrive niente", ns2.rec, None)
from calliope.conserva import CAMPI_TESTO, togli_testo  # noqa: E402
r = togli_testo({"testo": "x", "risposta": "y", "pronte": [{"id": "lavori.avviato"}]})
verifica("conservazione: senza parole le pronte restano (solo id)", r["pronte"],
         [{"id": "lavori.avviato"}])

# ── misura ──
AV = OGGI[("lavori.avviato", ())]


def turno(chi, risposta, giorno="2026-10-12", **k):
    return {"inizio": f"{giorno}T10:00:00", "voce": {"id": chi}, "risposta": risposta, **k}


turni = ([turno("anna", AV)] * 4 + [turno("anna", "Sono le 10.")] * 2
         + [turno("bruno", AV)] + [turno("anna", AV, giorno="2026-10-13")]
         + [turno("anna", "Fuori ci sono 18 gradi.")])
r = F.riassunto(turni)
g = r["giorni"]["2026-10-12"]
verifica("misura: pronte ripetute (stessa persona e giorno), modello con i numeri tolti",
         (g["pronte"]["n"], g["pronte"]["ripetute"], g["modello"]["n"], g["modello"]["ripetute"]),
         (5, 3, 3, 1))
verifica("contrari: un'altra persona e un altro giorno non sono ripetizioni",
         (r["giorni"]["2026-10-13"]["pronte"]["ripetute"], g["pronte"]["n"] - g["pronte"]["ripetute"]),
         (0, 2))
lunga = [turno("anna", AV)] + [turno("anna", f"Risposta numero {k} diversa {'x' * k}.")
                                for k in range(F.FINESTRA)] + [turno("anna", AV)]
verifica("contrario: oltre le ultime 20 risposte non è una ripetizione",
         F.riassunto(lunga)["totale"]["pronte"]["ripetute"], 0)
senza = [{"inizio": "2026-10-12T10:00", "voce": {"id": "minore"}, "risposta": None,
          "pronte": [{"id": "lavori.nessuno", "tono": "normale", "variante": 0, "breve": False}]}] * 2
verifica("misura: senza parole (minore) per id e variante",
         F.riassunto(senza)["totale"]["pronte"]["ripetute"], 1)
verifica("contrario: una risposta del modello senza parole non si conta",
         F.riassunto([{"inizio": "2026-10-12T10:00", "risposta": None}] * 3)["totale"]["tutte"]["n"],
         0)
ombra = [turno("anna", AV, pronte=[{"id": "lavori.avviato", "tono": "normale",
                                    "ombra": {"variante": i % 3, "breve": False}}])
         for i in range(3)]
rr = F.riassunto(ombra)["totale"]
verifica("misura: in ombra la stima con le varianti (3 dette uguali, 3 varianti diverse)",
         (rr["pronte"]["ripetute"], rr["stima_ombra"]["ripetute"], rr["ombra"]), (2, 0, 3))
verifica("misura: la cortesia di prima del 12/10 è una frase pronta",
         F.riassunto([{"inizio": "2026-10-12T10:00", "voce": {"id": "a"}, "esito": "cortesia",
                       "risposta": "Prego!"}])["totale"]["pronte"]["n"], 1)
txt = F.testo(F.riassunto(turni * 10))
verifica("stato --turni: la sezione con l'avviso sopra l'obiettivo",
         ("pronte" in txt, "sopra l'obiettivo" in txt), (True, True))
verifica("stato --turni: registro vuoto", F.testo(F.riassunto([])).endswith("nessuna risposta "
                                                                          "nel registro"), True)

# ── campione per chi amministra ──
c = F.campione(30)
verifica("campione: 30 forme", len(c), 30)
verifica("campione: tutti gli id non bloccati", {x["id"] for x in c},
         {v.id for v in F.CATALOGO.values() if not v.bloccata})
verifica("campione: nessuna classe bloccata, nessun segnaposto rimasto, mai la base",
         any(F.CATALOGO[x["id"]].bloccata or "{" in x["testo"] or x["testo"] == x["base"]
             for x in c), False)
verifica("campione: sempre lo stesso a parità di seme", F.campione(30) == c, True)
verifica("contrario: un altro seme, un altro campione", F.campione(30, seme=7) != c, True)
tmp = Path(tempfile.mkdtemp(prefix="calliope-frasi-")) / "campione.md"
verifica("campione: il comando scrive il file", (F.main(["--campione", "--file", str(tmp)]),
                                                tmp.read_text(encoding="utf-8").count("[ ]")),
         (0, 30))
verifica("contrario: senza opzioni il comando spiega e esce con 1", F.main([]), 1)

# ── cortesia ──
F.FRASI.__init__("ombra")
co = Cortesia()
verifica("cortesia in ombra: la rotazione di prima", [co.risposta("grazie", None, "normale",
                                                                  persona="a")
                                                      for _ in range(5)],
         ["Prego!", "Figurati.", "Di niente.", "A disposizione.", "Prego!"])
F.FRASI.__init__("attivo")
co = Cortesia()
ira = []
for _ in range(4):
    ira.append(co.risposta("grazie", "ironico", None, persona="a"))
    F.FRASI.detta(ira[-1])
irb = co.risposta("grazie", "ironico", None, persona="b")
verifica("cortesia attiva: per persona, frasi nuove del catalogo",
         (len(set(ira)), irb, ira[3] in RISPOSTE["ironico"]["grazie"]),
         (4, "Prego, lo metto in conto.", False))
verifica("cortesia attiva: le frasi nuove preparate all'avvio",
         "Prego. Accetto anche applausi." in co.frasi(["ironico"]), True)
F.FRASI.__init__("ombra")
verifica("contrario: in ombra non si preparano frasi in più",
         "Prego. Accetto anche applausi." in Cortesia().frasi(["ironico"]), False)

# ── configurazione ──
verifica("configurazione: ombra per predefinito, 6 turni", (Config().frasi_varianti,
                                                          Config().frasi_breve_turni),
         ("ombra", 6))
try:
    VALIDATORI["frasi_varianti"]("acceso")
    verifica("contrario: «acceso» rifiutato", False, True)
except ValueError:
    verifica("contrario: «acceso» rifiutato", True, True)
cf = Config()
cf.frasi_varianti, cf.frasi_breve_turni, cf.tono = "attivo", 2, "ironico"
fc = F.Frasi().configura(cf)
verifica("configura: modo, turni e tono della casa", (fc.modo, fc.breve_turni, fc.tono_casa),
         ("attivo", 2, "ironico"))

print(f"\n{'Tutto ok' if not errori else f'{errori} errori'}")
sys.exit(1 if errori else 0)
