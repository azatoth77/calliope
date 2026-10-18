import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della rotazione delle frasi pronte (18/10, issue #158, calliope/frasi.py).

Caso vero del 18/10 (lettura di #28): con `frasi_varianti: attivo` le frasi pronte si ripetevano
37,5 volte ogni 100, tutte su `cortesia.grazie` e `cortesia.conferma` con la variante 0, per due
difetti della rotazione: una voce sconosciuta (persona None) non ruotava mai, e dopo un riavvio
la rotazione ripartiva da capo mentre la misura conta l'intera giornata.

Qui: due «grazie» di fila da una voce sconosciuta danno due frasi diverse, in attivo e nella
variante scelta in ombra, senza forma breve; la misura (`riassunto`, i turni senza parole come li
scrive TurnLog) le conta senza ripetizioni. Dopo un riavvio simulato (`Frasi.riprendi` dal
registro dei turni di oggi) la stessa persona non riceve la variante appena detta, e anche la
forma breve riprende. Contrari: niente su disco per una voce sconosciuta (Frasi non scrive
file; un turno di ospite o di un conoscente non si rilegge; il registro dell'ospite senza
parole), i turni di ieri non contano, righe rotte e cartella assente non fermano l'avvio, main
la chiama dopo `configura`.
"""

import datetime
import json
import tempfile
from pathlib import Path

from calliope import frasi as F
from calliope.cortesia import Cortesia
from calliope.turnlog import TurnLog

errori = 0


def verifica(nome, ottenuto, atteso):
    global errori
    ok = ottenuto == atteso
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome} → {ottenuto!r}" + ("" if ok else f"  (atteso {atteso!r})"))


OGGI = datetime.date.today()
GRAZIE = F.CATALOGO["cortesia.grazie"]


def grazie(fr, co, persona, tono="normale"):
    """Un «grazie» come nel ciclo: il turno, la scelta della cortesia, l'uscita unica."""
    fr.inizio_turno(persona, tono)
    testo = co.risposta("grazie", tono, None, persona=persona)
    return testo, fr.detta(testo)


def riprendi(fr, cartella, **k):
    """`Frasi.riprendi` se c'è (su main no: la prova fallisce senza sollevare)."""
    f = getattr(fr, "riprendi", None)
    return f(cartella, **k) if f is not None else None


def turno(ora, persona=None, livello="familiare", pronte=(), risposta="x", conoscente=False):
    voce = {}
    if persona is not None:
        voce = {"id": persona, **({"conoscente": True} if conoscente else {"nome": persona})}
    return {"inizio": ora.isoformat(timespec="seconds"), "voce": voce, "livello": livello,
            "esito": "cortesia", "risposta": risposta, "pronte": [dict(p) for p in pronte]}


# ── voce sconosciuta (punto 1 della issue) ──
F.FRASI.__init__("attivo", breve_turni=6)
co = Cortesia()
a, da = grazie(F.FRASI, co, None)
b, db = grazie(F.FRASI, co, None)
verifica("sconosciuta, attivo: due «grazie» di fila, due frasi diverse", a != b, True)
verifica("sconosciuta, attivo: due varianti diverse nel registro",
         (da[0].get("variante"), db[0].get("variante")) in ((0, 1), (1, 0)), True)
verifica("sconosciuta: mai la forma breve (chi parla può essere un altro)",
         [d[0].get("breve") for d in (da, db)], [False, False])
seq = [a, b] + [grazie(F.FRASI, co, None)[0] for _ in range(4)]
verifica("sconosciuta: mai una delle ultime due",
         all(seq[i] not in seq[i - 2:i] for i in range(2, len(seq))), True)
verifica("le forme dette sono quelle del catalogo",
         {a, b} <= set(GRAZIE.forme("normale")), True)

F.FRASI.__init__("ombra", breve_turni=6)
co = Cortesia()
_, oa = grazie(F.FRASI, co, None)
_, ob = grazie(F.FRASI, co, None)
verifica("sconosciuta, ombra: la variante scelta gira (la stima della misura)",
         oa[0]["ombra"]["variante"] != ob[0]["ombra"]["variante"], True)

# La misura, coi turni come li scrive TurnLog per un ospite (senza parole, le pronte restano)
cart = Path(tempfile.mkdtemp(prefix="calliope-rotazione-"))
F.FRASI.__init__("attivo", breve_turni=6)
co = Cortesia()
log = TurnLog(str(cart), 60)
ora = datetime.datetime.combine(OGGI, datetime.time(10, 0))
dette = []
for k in range(4):
    testo, info = grazie(F.FRASI, co, None)
    dette.append(testo)
    log.write(turno(ora + datetime.timedelta(minutes=k), livello="ospite", pronte=info,
                    risposta=testo))
scritti = [json.loads(r) for r in (cart / f"turni-{OGGI.isoformat()}.jsonl")
           .read_text(encoding="utf-8").splitlines()]
verifica("ospite nel registro: nessuna parola, le pronte senza testo",
         ([t.get("risposta") for t in scritti], any(a in json.dumps(t, ensure_ascii=False)
                                                    for t in scritti for a in dette)),
         ([None] * 4, False))
r = F.riassunto(scritti)["totale"]["pronte"]
verifica("misura: quattro «grazie» di una voce sconosciuta, nessuna ripetizione",
         (r["n"], r["ripetute"]), (4, 0))

# ── niente su disco per una voce sconosciuta (decisione 0031) ──
prima = sorted(p.name for p in cart.iterdir())
F2 = F.Frasi("attivo", breve_turni=6)
n = riprendi(F2, str(cart))
verifica("contrario: i turni di un ospite non si rileggono", n, 0)
verifica("contrario: la rotazione anonima dopo un riavvio riparte (era solo in memoria)",
         F2._persone.get(F.ANONIMA) if hasattr(F, "ANONIMA") else "manca ANONIMA", None)
grazie(F2, Cortesia(), None)
verifica("contrario: Frasi non scrive niente nella cartella dei dati",
         sorted(p.name for p in cart.iterdir()), prima)
log.write(turno(ora + datetime.timedelta(minutes=9), "con-1", livello="ospite",
                pronte=[{"id": "cortesia.grazie", "tono": "normale", "variante": 0,
                         "breve": False}], conoscente=True))
verifica("contrario: un conoscente (livello ospite) non si rilegge",
         riprendi(F.Frasi("attivo"), str(cart)), 0)

# ── riavvio (punto 2 della issue) ──
cart2 = Path(tempfile.mkdtemp(prefix="calliope-rotazione-"))
log2 = TurnLog(str(cart2), 60)
F.FRASI.__init__("attivo", breve_turni=0)
co = Cortesia()
prima_dette = []
for k in range(2):
    testo, info = grazie(F.FRASI, co, "anna")
    prima_dette.append(testo)
    log2.write(turno(ora + datetime.timedelta(minutes=k), "anna", pronte=info, risposta=testo))
# Il riavvio: un catalogo nuovo e una cortesia nuova, come all'avvio di main
F.FRASI.__init__("attivo", breve_turni=0)
verifica("riavvio: la rotazione di una persona ripresa dai turni di oggi",
         riprendi(F.FRASI, str(cart2)), 1)
dopo, info_dopo = grazie(F.FRASI, Cortesia(), "anna")
verifica("riavvio: la stessa persona non riceve le varianti appena dette",
         dopo in prima_dette, False)
verifica("riavvio: la prossima della rotazione, come senza riavvio",
         dopo, GRAZIE.forme("normale")[2])
log2.write(turno(ora + datetime.timedelta(minutes=5), "anna",
                 pronte=info_dopo, risposta=dopo))
tutti = [json.loads(x) for x in (cart2 / f"turni-{OGGI.isoformat()}.jsonl")
         .read_text(encoding="utf-8").splitlines()]
verifica("misura: la giornata col riavvio in mezzo, nessuna ripetizione",
         F.riassunto(tutti)["totale"]["pronte"]["ripetute"], 0)
F.FRASI.__init__("attivo", breve_turni=0)
riprendi(F.FRASI, str(cart2))
verifica("contrario: un'altra persona non eredita la rotazione di anna",
         grazie(F.FRASI, Cortesia(), "bruno")[1][0]["variante"], 0)

# La forma breve riprende anche lei (nei turni e nell'ora)
cart3 = Path(tempfile.mkdtemp(prefix="calliope-rotazione-"))
adesso = datetime.datetime.now().replace(microsecond=0)
fp = F.Frasi("attivo", breve_turni=3)
fp.inizio_turno("anna", "normale")
pe = dict(cosa="È un lavoro di programmazione", agente="sulla DGX", coda="", carico="",
          stima="Ci vorranno alcuni minuti", dopo="")
p1 = fp.detta(fp.scegli("lavori.proposta", **pe))
TurnLog(str(cart3), 60).write(turno(adesso, "anna", pronte=p1))
fq = F.Frasi("attivo", breve_turni=3)
riprendi(fq, str(cart3), oggi=adesso.date())
fq.inizio_turno("anna", "normale")
verifica("riavvio: la seconda proposta di fila è breve anche dopo il riavvio",
         fq.detta(fq.scegli("lavori.proposta", **pe))[0]["breve"], True)

# ── contrari della ripresa ──
cart4 = Path(tempfile.mkdtemp(prefix="calliope-rotazione-"))
ieri = OGGI - datetime.timedelta(days=1)
TurnLog(str(cart4), 60).write(turno(datetime.datetime.combine(ieri, datetime.time(22, 0)),
                                    "anna", pronte=[{"id": "cortesia.grazie", "tono": "normale",
                                                     "variante": 0, "breve": False}]))
verifica("contrario: i turni di ieri non contano (la misura è per giorno)",
         riprendi(F.Frasi("attivo"), str(cart4)), 0)
(cart4 / f"turni-{OGGI.isoformat()}.jsonl").write_text(
    '{"voce": {"id": "anna"\n' + json.dumps(turno(ora, "anna", pronte=[
        {"id": "cortesia.grazie", "tono": "normale", "variante": 0, "breve": False},
        {"id": "inventato.id", "tono": "normale", "variante": 0}])) + "\n", encoding="utf-8")
verifica("contrario: una riga rotta e un id sconosciuto non fermano la ripresa",
         riprendi(F.Frasi("attivo"), str(cart4)), 1)
verifica("contrario: cartella assente o registro spento → niente",
         (riprendi(F.Frasi("attivo"), str(cart4 / "manca")), riprendi(F.Frasi("attivo"), None)),
         (0, 0))
fs = F.Frasi("attivo")
(cart4 / f"turni-{OGGI.isoformat()}.jsonl").write_text(json.dumps(turno(ora, "anna", pronte=[
    {"id": "cortesia.grazie"}])) + "\n", encoding="utf-8")
riprendi(fs, str(cart4))
verifica("contrario: un id senza tono (frasi_varianti spento) non fa girare niente",
         fs._persone.get("anna", {}).get("giri"), {})

# Mai sollevare (revisione della PR #162): l'avvio non si ferma per il registro
def sicura(fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        return f"sollevata {type(e).__name__}"


G = {"id": "cortesia.grazie", "tono": "normale", "variante": 1, "breve": False}
cart5 = Path(tempfile.mkdtemp(prefix="calliope-rotazione-"))
buona = json.dumps(turno(ora, "anna", pronte=[G]), ensure_ascii=False)
tronca = json.dumps(turno(ora, "anna", pronte=[G], risposta="Ciao, è tutto"),
                    ensure_ascii=False).encode("utf-8")
tronca = tronca[:tronca.index("è".encode("utf-8")) + 1]          # metà della «è»
(cart5 / f"turni-{OGGI.isoformat()}.jsonl").write_bytes(buona.encode("utf-8") + b"\n" + tronca)
fu = F.Frasi("attivo")
verifica("contrario: un UTF-8 troncato dentro una lettera accentata non solleva",
         sicura(lambda: riprendi(fu, str(cart5))), 1)
verifica("UTF-8 troncato: la riga buona conta lo stesso",
         sicura(lambda: fu._persone["anna"]["giri"]), {("cortesia.grazie", "normale", False): 1})
storte = [
    {"inizio": ora.isoformat(), "voce": {"id": "anna"}, "pronte": "cortesia.grazie"},
    {"inizio": ora.isoformat(), "voce": {"id": 5}, "pronte": [G]},
    {"inizio": ora.isoformat(), "voce": {"id": ["anna"]}, "pronte": [G]},
    {"inizio": ora.isoformat(), "voce": "anna", "pronte": [G]},
    {"inizio": 12, "voce": {"id": "anna"}, "pronte": [
        {"id": ["cortesia.grazie"], "tono": "normale"}, {"id": "cortesia.grazie", "tono": 3},
        {"id": {"x": 1}, "tono": None}, "cortesia.grazie", None]},
    ["voce", {"id": "anna"}],
    {"inizio": ora.isoformat(), "voce": {"id": "con-2", "conoscente": True}, "pronte": [G]},
]
(cart5 / f"turni-{OGGI.isoformat()}.jsonl").write_text(
    "\n".join(json.dumps(x) for x in storte) + "\n" + buona + "\n", encoding="utf-8")
fw = F.Frasi("attivo")
verifica("contrario: valori del tipo sbagliato (pronte, voce.id, id, tono) non sollevano",
         sicura(lambda: riprendi(fw, str(cart5))), 1)
verifica("tipi sbagliati: conta solo la riga buona, i turni di anna sì",
         sicura(lambda: (fw._persone["anna"]["giri"], fw._persone["anna"]["turno"])),
         ({("cortesia.grazie", "normale", False): 1}, 3))
verifica("contrario: un conoscente senza `livello` non si rilegge",
         sicura(lambda: "con-2" in fw._persone), False)
fg = F.Frasi("attivo")
fg._riprendi = lambda *a: 1 / 0
verifica("contrario: un guasto qualunque dentro vale 0, senza sollevare",
         sicura(lambda: riprendi(fg, str(cart5))), 0)

# main riprende la rotazione all'avvio, subito dopo la configurazione
src = (Path(__file__).resolve().parent.parent / "calliope" / "main.py").read_text(encoding="utf-8")
i, j = src.find("frasi.FRASI.configura(cfg)"), src.find("frasi.FRASI.riprendi(cfg.turn_log_dir)")
verifica("main: riprende dai turni dopo configura", 0 <= i < j, True)
verifica("main: la ripresa dentro un try (un guasto non ferma l'avvio)",
         j > 0 and src.rfind("try:", i, j) > i and "except Exception" in src[j:j + 400], True)

print(f"\n{'Tutto ok' if not errori else f'{errori} errori'}")
sys.exit(1 if errori else 0)
