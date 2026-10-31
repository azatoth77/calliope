import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Le mini-app della libreria dello Studio a secco (31/10, issue #297, parte 2, epic #251, decisione
0035 punto 46; calliope/studio/libreria/miniapp.py e miniapp/, schermi/giochi.py, tools/studio.py
`studio_attivita`, schermi/tocchi.py). Persone di fantasia (Leo, il tutore Andrea, Bruno).

1. **La serie**: otto mini-app, almeno due per materia (Chimica, Fisica, Informatica, Biologia),
   nei tre tipi (esplora, quiz, percorso), ognuna legata a una scheda che c'è; il caricamento
   (manifesto valido, gioco puro con la macchina, nome `libreria_<cartella>`, i comandi della
   scheda forme vere della macchina) coi contrari.
2. **Test e prova di fumo** di ogni mini-app (`calliope/agenti/fumo_js.mjs` col motore vero: le
   fasi, 20 partite fino alla fine, il palco nei due orientamenti), con Node.
3. **La verità** di ciò che ogni mini-app mostra (`verita_miniapp.mjs` stampa dati e frasi, qui i
   conti e le tabelle scritti a parte): elementi e livelli, reazioni bilanciate, densità e
   galleggiamento, moto con le conversioni, bit e binario, strutture della cellula, osmosi.
4. **Aprirle**: `Giochi.avvia` coi file della libreria (il riquadro da quei byte, mai
   dall'archivio), il tool `studio_attivita` (a voce sceglie il codice dai titoli, il tocco col
   bersaglio), la prova aperta, i file cambiati, il tocco `studio_attivita` nell'elenco chiuso;
   attraverso Brain.

    python prove/prova_studio_miniapp.py
"""

import contextlib
import copy
import datetime
import io
import json
import shutil
import subprocess
import tempfile
import types
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI.parent))

from calliope import politica, valore  # noqa: E402
from calliope import studio as S  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.schermi import tocchi as T  # noqa: E402
from calliope.studio.libreria import indice as I  # noqa: E402
from calliope.studio.libreria import miniapp as MA  # noqa: E402
from calliope.tools import studio as TS  # noqa: E402
from calliope.tools.registry import ToolRegistry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402
import verita_libreria as VL  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio and not ok
                                                else ""), flush=True)


TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-miniapp-"))
LIB = I.Libreria.carica()

# ═══════════════════════════ 1. la serie ═══════════════════════════
print("— la serie")
verifica("la libreria si carica senza errori", not LIB.errori, "; ".join(LIB.errori[:3]))
APP = {k: LIB.contenuti[k] for k in LIB.app}
per_materia: dict = {}
for v in APP.values():
    per_materia.setdefault(v["materia"], []).append(v["id"])
verifica("otto mini-app, almeno due per materia",
         len(APP) >= 8 and set(per_materia) == {"Chimica", "Fisica", "Informatica", "Biologia"}
         and min(len(x) for x in per_materia.values()) >= 2, str(per_materia))
verifica("i tre tipi della issue: da esplorare, con il quiz, percorso guidato",
         {v["tipo_app"] for v in APP.values()} == {"esplora", "quiz", "percorso"})
verifica("ogni mini-app serve schede della libreria della sua materia",
         all(LIB.contenuti[s]["tipo"] == "scheda" and LIB.contenuti[s]["materia"] == v["materia"]
             for v in APP.values() for s in v["schede"]))
verifica("ogni cartella in miniapp/ è di una mini-app della libreria (niente cartelle orfane)",
         {p.name for p in MA.CARTELLA.iterdir() if p.is_dir()}
         == {v["estensione"] for v in APP.values()})
verifica("giochi puri per un giocatore, che non salvano niente e non sono condivisi",
         all((a.manifesto["scheda"]["giocatori"] == {"min": 1, "max": 1})
             and not a.manifesto["scheda"]["salva"] and not a.manifesto["scheda"]["condivisa"]
             and a.manifesto["permessi"] == politica_vuoti for a in LIB.app.values())
         if (politica_vuoti := next(iter(LIB.app.values())).manifesto["permessi"]) is not None
         else False)
verifica("i comandi della scheda della libreria sono forme vere della macchina",
         all(set(c.lower() for c in v["comandi"]) <= LIB.app[k].forme() for k, v in APP.items()))
verifica("l'indice le propone con la loro scheda (dopo scheda e carte)",
         [p["tipo"] for p in I.scegli(LIB, [{"id": 1, "numero": 1, "titolo": "La struttura "
                                              "dell'atomo"}], "Chimica")]
         == ["scheda", "mazzo", "miniapp"])
# Contrari del caricamento
cart = TMP / "app"
shutil.copytree(MA.CARTELLA / "atomo", cart / "atomo")
a, e = MA.carica("atomo", ["un protone in più"], cart)
verifica("una copia intatta si carica", a is not None and not e, str(e))
verifica("contrario: un comando della scheda che la macchina non ha",
         any("non ha" in x for x in MA.carica("atomo", ["dammi la risposta"], cart)[1]))
m = json.loads((cart / "atomo" / "manifesto.json").read_text("utf-8"))
for nome, cambia in (("un permesso (legge l'agenda)", lambda d: d.update(permessi={"legge": ["agenda"]})),
                     ("il nome diverso dalla cartella", lambda d: d.update(nome="libreria_altro")),
                     ("i dati salvati", lambda d: d["scheda"].update(salva=True)),
                     ("senza la macchina", lambda d: d["scheda"].pop("macchina")),
                     ("con «Gioco anch'io»", lambda d: d["scheda"]["macchina"].pop("anchio"))):
    d = copy.deepcopy(m)
    cambia(d)
    (cart / "atomo" / "manifesto.json").write_text(json.dumps(d), "utf-8")
    verifica(f"contrario: {nome}", MA.carica("atomo", [], cart)[0] is None,
             str(MA.carica("atomo", [], cart)[1]))
(cart / "atomo" / "manifesto.json").write_text(json.dumps(m), "utf-8")
js = (cart / "atomo" / "logica.js").read_text("utf-8")
(cart / "atomo" / "logica.js").write_text(js + "\nfetch('https://esempio.org');\n", "utf-8")
verifica("contrario: un rischio nell'analisi statica (fetch)", MA.carica("atomo", [], cart)[0] is None)
(cart / "atomo" / "logica.js").write_text(js, "utf-8")
a, _ = MA.carica("atomo", [], cart)
(cart / "atomo" / "logica.js").write_text(js + "\n// cambiato\n", "utf-8")
verifica("l'impronta: un file cambiato dopo il caricamento non è più intatto",
         a is not None and not a.intatta())

# ═══════════════════════════ 2. test e prova di fumo ═══════════════════════════
print("— test e prova di fumo")
NODE = shutil.which("node")
if NODE is None:
    print("SALTATA IN PARTE: node non c'è")
else:
    import prova_agente_guida as G
    for k, v in sorted(APP.items()):
        sb = G.sandbox(TMP / "fumo", v["estensione"])
        for f in (MA.CARTELLA / v["estensione"]).iterdir():
            sb.scrivi(f.name, f.read_text("utf-8"))
        r = sb.test()
        verifica(f"{v['estensione']}: i test e la prova di fumo (fasi, partite fino alla fine, "
                 "palco)", r["passano"] and "ok prova di fumo del gioco" in r["uscita"]
                 and "FALLITO" not in r["uscita"], r["uscita"][-600:])

# ═══════════════════════════ 3. la verità ═══════════════════════════
print("— la verità")
if NODE is not None:
    out = subprocess.run([NODE, str(QUI / "verita_miniapp.mjs"), str(MA.CARTELLA)],
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    V = json.loads(out.stdout) if out.returncode == 0 else {}
    verifica("verita_miniapp.mjs legge tutte le mini-app", out.returncode == 0, out.stderr[-400:])

    # Atomo: simbolo, nome, isotopo più comune, neutroni e livelli
    NOMI = {"H": "Idrogeno", "He": "Elio", "Li": "Litio", "Be": "Berillio", "B": "Boro",
            "C": "Carbonio", "N": "Azoto", "O": "Ossigeno", "F": "Fluoro", "Ne": "Neon",
            "Na": "Sodio", "Mg": "Magnesio", "Al": "Alluminio", "Si": "Silicio", "P": "Fosforo",
            "S": "Zolfo", "Cl": "Cloro", "Ar": "Argon", "K": "Potassio", "Ca": "Calcio"}
    # Il numero di massa dell'isotopo più abbondante in natura
    PIU_COMUNE = {"H": 1, "He": 4, "Li": 7, "Be": 9, "B": 11, "C": 12, "N": 14, "O": 16, "F": 19,
                  "Ne": 20, "Na": 23, "Mg": 24, "Al": 27, "Si": 28, "P": 31, "S": 32, "Cl": 35,
                  "Ar": 40, "K": 39, "Ca": 40}
    at = V.get("atomo", {})
    ok = len(at.get("elementi", [])) == 20
    err = []
    for z, (el, d) in enumerate(zip(at.get("elementi", []), at.get("descrizioni", [])), 1):
        simb, nome, a_ = el
        if VL.ELEMENTI.get(simb, (0,))[0] != z or NOMI.get(simb) != nome or PIU_COMUNE[simb] != a_:
            err.append(f"Z {z}: {el}")
        if d["neutroni"] != VL.calcola("neutroni", {"A": a_, "Z": z}) or \
                "-".join(map(str, d["livelli"])) != VL.calcola("elettroni_per_livello", {"Z": z}):
            err.append(f"Z {z}: neutroni o livelli {d}")
        if f"{z} protoni" not in d["testo"] and z > 1 or f"{a_ - z} neutron" not in d["testo"]:
            err.append(f"Z {z}: il testo «{d['testo']}»")
    verifica("atomo: i 20 elementi (Z, simbolo, nome, isotopo più comune), neutroni e livelli "
             "nel testo", ok and not err, "; ".join(err[:3]))

    # Bilancia: solo il coefficiente giusto bilancia, e i conti degli atomi
    err = []
    for x in V.get("bilancia", []):
        r = x["r"]
        for pr in x["prove"]:
            sin = " + ".join(f"{pr['c'] if c is None else c} {f}" for c, f in r["sinistra"])
            des = " + ".join(f"{pr['c'] if c is None else c} {f}" for c, f in r["destra"])
            reaz = f"{sin} -> {des}"
            bil = VL.bilanciata(reaz)
            if bil != (pr["c"] == r["giusto"]):
                err.append(f"{reaz}: bilanciata {bil}, giusto {r['giusto']}")
            el = x["elemento"]
            vero = [sum((pr["c"] if c is None else c) * VL.formula_in_atomi(f).get(el, 0)
                        for c, f in r[lato]) for lato in ("sinistra", "destra")]
            if [pr["sinistra"], pr["destra"]] != vero or \
                    f"{el}: {vero[0]} a sinistra, {vero[1]} a destra" != pr["riga"]:
                err.append(f"{reaz}: conto {pr['riga']} contro {vero}")
    verifica("bilancia: solo il coefficiente giusto bilancia la reazione, e gli atomi contati "
             "sono quelli veri", len(V.get("bilancia", [])) >= 4 and not err, "; ".join(err[:3]))

    # Densità: d = m/V, coerente col materiale vero, galleggia sotto 1, mai 1
    RIF = {"sughero": (0.12, 0.30), "abete": (0.35, 0.55), "legno di abete": (0.35, 0.55),
           "ghiaccio": (0.90, 0.93), "pvc": (1.30, 1.45), "alluminio": (2.65, 2.75),
           "ferro": (7.8, 7.9), "rame": (8.9, 9.0), "cera d'api": (0.95, 0.97),
           "vetro": (2.4, 2.8), "polistirolo espanso": (0.01, 0.05), "olio d'oliva": (0.90, 0.93),
           "gomma": (1.1, 1.2)}
    den = V.get("densita", {})
    err = []
    for c in den.get("conti", []):
        d = VL.calcola("densita", {"m": c["m"], "V": c["V"]})
        mat = c["materiale"].lower()
        lo, hi = next((r for k, r in RIF.items() if k == mat or k in mat), (None, None))
        if lo is None or not lo <= d <= hi:
            err.append(f"{mat}: {d:.2f} fuori da {lo}–{hi}")
        if abs(c["d"] - d) > 1e-9 or c["cifre"] != f"{d:.2f}".replace(".", ","):
            err.append(f"{mat}: d {c['d']} «{c['cifre']}»")
        if c["destino"] != ("galleggia" if d < den["acqua"] else "affonda") or \
                c["cifre"] not in c["conto"] or c["destino"] not in c["conto"]:
            err.append(f"{mat}: «{c['conto']}»")
        if abs(d - 1) < 0.02:
            err.append(f"{mat}: densità troppo vicina all'acqua ({d:.2f})")
    verifica("densità: m : V giusta, coerente col materiale vero, galleggia sotto 1 g/cm³, mai "
             "vicina a 1", den.get("acqua") == 1 and len(den.get("conti", [])) >= 10 and not err,
             "; ".join(err[:3]))

    # Moto: s = v × t con le conversioni, e una sola opzione giusta
    err = []
    for x in V.get("moto", []):
        p = x["p"]
        lung = p["unita_v"].split("/")[0]
        tempo = {"s": "s", "min": "min", "h": "h"}[p["unita_v"].split("/")[1]]
        t_ = VL.converti(p["t"], p["unita_t"], tempo)
        s = p["v"] * t_
        s = VL.converti(s, {"cm": "cm", "m": "m", "km": "km"}[lung], p["unita_s"]) \
            if lung != p["unita_s"] else s
        giuste = [o for o in p["opzioni"] if abs(o - s) < 1e-6 * max(1, s)]
        if len(giuste) != 1 or abs(p["opzioni"][p["giusta"]] - s) > 1e-6 * max(1, s):
            err.append(f"{p['cosa']}: s vera {s}, opzioni {p['opzioni']}, giusta {p['giusta']}")
        if abs(x["risolto"]["s"] - s) > 1e-6 * max(1, s) or \
                VL.numeri_nel_testo(x["conto"])[-1:] != [p["opzioni"][p["giusta"]]]:
            err.append(f"{p['cosa']}: «{x['conto']}»")
    conv = any(p["p"]["unita_v"] == "km/h" for p in V.get("moto", []))
    verifica("moto: lo spazio vero (s = v × t con le conversioni), una sola opzione giusta, il "
             "conto detto", len(V.get("moto", [])) >= 4 and conv and not err, "; ".join(err[:3]))

    # Bit e binario
    b = V.get("bit", {})
    err = []
    if b.get("dati", {}).get("pesi") != [2 ** n for n in range(8)]:
        err.append("pesi")
    for x in b.get("stati", []):
        val = sum(2 ** n for n, on in enumerate(x["acceso"]) if on)
        if x["valore"] != val or x["cifre"] != format(val, "08b") or not \
                x["somma"].endswith(f"= {val}"):
            err.append(str(x))
    verifica("bit: i pesi sono le potenze di 2, il valore e le otto cifre giusti",
             not err, "; ".join(err[:3]))
    bi = V.get("binario", {})
    err = []
    for e in bi.get("esempi", []):
        d = e["decimale"]
        if e["binario"] != VL.calcola("decimale_in_binario", {"decimale": d}):
            err.append(f"{d}: {e['binario']}")
        q, ok_div = d, True
        for div in e["divisioni"]:
            vals = list(div.values()) if isinstance(div, dict) else div
            nums = [n for n in vals if isinstance(n, int)]
            if q // 2 not in nums or q % 2 not in nums:
                ok_div = False
            q //= 2
        if not ok_div:
            err.append(f"{d}: divisioni {e['divisioni']}")
    for q in bi.get("domande", []):
        op = q["opzioni"]
        vero = (str(VL.calcola("binario_in_decimale", {"binario": q["numero"]})) if q["verso"] == "bd"
                else VL.calcola("decimale_in_binario", {"decimale": q["numero"]}))
        if op[q["giusta"]] != vero or len(set(op)) != len(op) or op.count(vero) != 1:
            err.append(f"{q['numero']}: {op} giusta {q['giusta']}")
        if any(i != q["giusta"] and not q["perche"][i] for i in range(len(op))):
            err.append(f"{q['numero']}: una risposta sbagliata senza il perché")
    verifica("binario: gli esempi (le divisioni per 2 e i resti), una sola risposta giusta per "
             "domanda, il perché di ogni sbagliata", len(bi.get("domande", [])) >= 6 and not err,
             "; ".join(err[:3]))

    # La cellula: dove sta ogni struttura, una tabella scritta qui
    DOVE = {"nucleo": {"animale", "vegetale"}, "mitocondrio": {"animale", "vegetale"},
            "cloroplasto": {"vegetale"}, "ribosoma": {"animale", "vegetale", "batterica"},
            "parete": {"vegetale", "batterica"}, "vacuolo": {"vegetale"},
            "membrana": {"animale", "vegetale", "batterica"},
            "reticolo": {"animale", "vegetale"}}
    FUNZIONE = {"fotosintesi": "cloroplasto", "entra ed esce": "membrana"}
    ce = V.get("cellula", {})
    err = []
    for s in ce.get("strutture", []):
        if set(s["in"]) != DOVE.get(s["id"]):
            err.append(f"{s['id']}: {s['in']}")
    for q in ce.get("domande", []):
        if "struttura" in q:
            if q["risposta"] != (q["cellula"] in DOVE[q["struttura"]]):
                err.append(f"{q['struttura']} in {q['cellula']}: {q['risposta']}")
        else:
            att = next((v for k, v in FUNZIONE.items() if k in q["testo"]), None)
            if q["giusta"] not in q["opzioni"] or (att and q["giusta"] != att):
                err.append(f"«{q['testo']}»: {q['giusta']}")
    verifica("cellula: in quali cellule c'è ogni struttura e le risposte del quiz",
             len(ce.get("strutture", [])) == 8 and len(ce.get("domande", [])) >= 6 and not err,
             "; ".join(err[:3]))

    # Osmosi: confronto con l'interno, il nome della soluzione, l'emolisi in acqua distillata
    os_ = V.get("osmosi", {})
    err = []
    for p in os_.get("passi", []):
        c, i = p["concentrazione"], os_["interna"]
        att = ("gonfia", "ipotonica", "entra") if c < i else ("uguale", "isotonica", "pari") \
            if c == i else ("raggrinzisce", "ipertonica", "esce")
        if (p["risposta"], p["tipo"], p["verso"]) != att or p["tipo"] not in p["perche"]:
            err.append(f"{c} %: {p['risposta']} {p['tipo']} {p['verso']}")
        if (c == 0) != ("emolisi" in p["perche"]):
            err.append(f"{c} %: l'emolisi solo in acqua distillata")
        if (c > i) != ("crenatura" in p["perche"]) or "soluti" not in p["perche"]:
            err.append(f"{c} %: la crenatura solo nell'ipertonica, e i soluti")
    verifica("osmosi: interna 0,9 %, ipo, iso e ipertonica con l'acqua che entra o esce, "
             "l'emolisi solo in acqua distillata",
             os_.get("interna") == 0.9 and {p["tipo"] for p in os_.get("passi", [])}
             == {"ipotonica", "isotonica", "ipertonica"} and not err, "; ".join(err[:3]))

# ═══════════════════════════ 4. aprirle ═══════════════════════════
print("— aprirle")
from calliope.schermi import Mittente  # noqa: E402
from calliope.schermi.giochi import Giochi  # noqa: E402


class Prof:
    def __init__(self, pid, name, admin=False, nascita=None, tutori=()):
        self.id, self.name, self.admin = pid, name, admin
        self.nascita, self.tutori, self.fascia, self.tipo = nascita, list(tutori), None, None
        self.level = "amministra" if admin else "familiare"


class Registro:
    def __init__(self, *profili):
        self.users = {p.name: p for p in profili}

    def by_id(self, pid):
        return next((p for p in self.users.values() if p.id == pid), None)

    def get(self, nome):
        return self.users.get(nome)


ANDREA, BRUNO = Prof("a1", "Andrea"), Prof("b1", "Bruno")
LEO = Prof("l1", "Leo", nascita="2011-03-01", tutori=["a1"])
REG = Registro(ANDREA, BRUNO, LEO)


class Hub:
    """L'hub degli schermi che serve a Giochi.avvia: il telefono di Leo."""
    stanza_predefinita = None

    def __init__(self):
        self.inviate = []
        self.eventi = []
        self.giochi = None

    def mittente(self, ctx):
        return Mittente(persona="l1", nome="Leo", livello="familiare", certo=True, schermo=1)

    def abbinati(self):
        return [{"id": 1, "nome": "telefono di Leo", "proprietario": "l1", "stanza": "telefono"}]

    def ricorda(self, card, mitt):
        pass

    def invia_a(self, sid, card, **kw):
        self.inviate.append((sid, card))
        return True

    def evento_a(self, sid, tipo, dati, **kw):
        self.eventi.append((sid, tipo, dati))
        return 1

    def schermo(self, sid, creato=None):
        return {"id": sid, "nome": "telefono di Leo"}


ORA = [datetime.datetime(2026, 10, 29, 16, 0)]
cfg = Config()
cfg.memory_db = str(TMP / "s.db")
cfg.studio_modo, cfg.studio_cartella, cfg.studio_lettura = "attivo", str(TMP / "studio"), False
cfg.turn_log_dir = str(TMP / "registro")
registro: list = []
st = S.Studio(cfg, registry=REG, log=registro.append, adesso=lambda: ORA[0])
st.avvia_lettura(None, avvia=False)
vid = st.crea_verifica(LEO, "Chimica", "2026-11-05")
st.aggiungi_argomento(LEO, vid, "La struttura dell'atomo", [], proposto=False)
st.conferma_argomenti(LEO, vid)
hub = Hub()
hub.giochi = Giochi(cfg, hub, None, log=lambda *a: None)
hub.giochi.speakers = REG          # i profili per id (senza estensioni: Giochi._profilo)
TOOLS = ToolRegistry()
for sp in TS.studio_specs():
    TOOLS.register(sp)


def ctx_di(prof, bersaglio=None):
    sc = types.SimpleNamespace(current_speaker=prof.name if prof else None, identified_by="voce",
                               minore_incerto=None,
                               current_level=prof.level if prof else "ospite",
                               profile_level=prof.level if prof else "ospite")
    c = ToolContext(cfg=cfg, speakers=REG, speaker_ctx=sc, speaker=None)
    c.studio, c.schermi = st, hub
    if bersaglio:
        c.tocco_bersaglio = {"studio": bersaglio}
    return c


def chiama(ctx, **args):
    return json.loads(TOOLS.call("studio_attivita", args, ctx, "familiare"))


verifica("studio_attivita: «sicuro», senza fonte, effetto E0, per familiari",
         politica.classe_di("studio_attivita").classe == politica.SICURO
         and politica.fonte_di("studio_attivita") is None
         and valore.effetto("studio_attivita", {"attivita": "x"}) == valore.E0
         and TOOLS.get("studio_attivita").levels == frozenset({"familiare", "amministra"}))
verifica("la scelta a voce: le parole dette contro i titoli e le chiavi (dati fidati)",
         TS.scegli_attivita(LIB, "costruisci l'atomo")[0] == "chimica-atomo-app"
         and TS.scegli_attivita(LIB, "i bit")[0] == "informatica-binario-app"
         and TS.scegli_attivita(LIB, "bilanciare le reazioni")[0] == "chimica-reazioni-app"
         and TS.scegli_attivita(LIB, "osmosi")[0] == "biologia-membrana-app"
         and TS.scegli_attivita(LIB, "la rivoluzione francese")[0] is None)
r = chiama(ctx_di(LEO), attivita="costruisci l'atomo")
card = hub.inviate[-1][1] if hub.inviate else {}
p = next(iter(hub.giochi.partite.values()), None)
verifica("a voce: «costruisci l'atomo» apre la mini-app sul telefono di Leo",
         r.get("ok") is not False and p is not None and p.nome == "libreria_atomo"
         and p.file == LIB.app["chimica-atomo-app"].file and card.get("doc", "").startswith(
             "/gioco/"), str(r)[:300])
doc = hub.giochi.documento(p.gettone) if p else None
verifica("il riquadro si compone dai file della libreria (senza archivio delle estensioni), "
         "con la CSP", doc is not None and "Costruisci" in doc[0] and "GIOCO" in doc[0]
         and "connect-src 'none'" in doc[1], str(doc)[:200] if doc else "None")
verifica("il registro: solo l'id dell'attività", any("chimica-atomo-app aperta" in x
                                                    for x in registro))
r = chiama(ctx_di(LEO), attivita="la rivoluzione francese")
verifica("a voce, un'attività che non c'è: dice quali ci sono, non apre niente",
         r.get("ok") is False and r.get("scegli") and "«Costruisci l'atomo»" in r["conferma"],
         str(r)[:300])
r = chiama(ctx_di(None), attivita="atomo")
verifica("l'ospite: lo Studio non si apre", r.get("ok") is False and r["conferma"] == TS.CHI_NO)
# Il tocco
pr = T.prepara({"tocco": "studio_attivita", "verifica": vid, "contenuto": "fisica-moto-app"},
               types.SimpleNamespace(studio=st), LEO)
verifica("il tocco «Apri»: studio_attivita col bersaglio scelto dal codice",
         pr.get("tool") == "studio_attivita" and pr["bersaglio"]["studio"] == {
             "verifica": vid, "contenuto": "fisica-moto-app"} and not T.senza_bersaglio(
             {"tocco": "studio_attivita", "bersaglio": pr["bersaglio"]})
         and T.non_ammesso({"tocco": "studio_attivita", "tool": "studio_attivita",
                            "argomenti": pr["argomenti"]}, TOOLS.get("studio_attivita")) is None,
         str(pr)[:300])
verifica("contrario: il tocco su un'attività che non c'è, sulla verifica di un altro",
         T.prepara({"tocco": "studio_attivita", "verifica": vid, "contenuto": "magia"},
                   types.SimpleNamespace(studio=st), LEO).get("_stato") == 404
         and T.prepara({"tocco": "studio_attivita", "verifica": vid, "contenuto": "fisica-moto-app"},
                       types.SimpleNamespace(studio=st), BRUNO).get("_stato") == 404)
verifica("contrario: senza il bersaglio il ciclo lo rifiuta",
         T.senza_bersaglio({"tocco": "studio_attivita", "bersaglio": {"studio": {"verifica": vid}}}))
r = chiama(ctx_di(LEO, pr["bersaglio"]["studio"]), attivita="Moto")
verifica("dal tocco: apre l'attività del bersaglio", r.get("ok") is not False and any(
    x.nome == "libreria_moto" for x in hub.giochi.partite.values()), str(r)[:200])
r = chiama(ctx_di(BRUNO, pr["bersaglio"]["studio"]), attivita="Moto")
verifica("contrario: il bersaglio con la verifica di un altro", r.get("ok") is False)
# La prova aperta
pv = st.crea_verifica(LEO, "Fisica", "2026-11-06")
aid = st.aggiungi_argomento(LEO, pv, "Il moto rettilineo uniforme", [], proposto=False)
st.conferma_argomenti(LEO, pv)
for i in range(3):
    st.aggiungi_domanda(LEO, pv, "vero_falso", f"Domanda {i}?", "vero", argomento=aid)
st.inizia_prova(LEO, pv)
r = chiama(ctx_di(LEO), attivita="bilancia la reazione")
verifica("con una prova aperta: niente attività, a voce e dal tocco",
         r.get("ok") is False and r["conferma"] == TS.ATTIVITA_PROVA
         and T.prepara({"tocco": "studio_attivita", "verifica": pv, "contenuto": "fisica-moto-app"},
                       types.SimpleNamespace(studio=st), LEO).get("_stato") == 409, str(r))
# Revisione della PR #366, nota 1: una prova aperta su UN'ALTRA verifica della persona
vb = st.crea_verifica(LEO, "Informatica", "2026-11-12")
st.aggiungi_argomento(LEO, vb, "Il sistema binario", [], proposto=False)
st.conferma_argomenti(LEO, vb)
pr_b = T.prepara({"tocco": "studio_attivita", "verifica": vb,
                  "contenuto": "informatica-binario-app"}, types.SimpleNamespace(studio=st), LEO)
r = chiama(ctx_di(LEO, {"verifica": vb, "contenuto": "informatica-binario-app"}), attivita="bit")
verifica("con una prova aperta su un'altra verifica: il tocco su una verifica libera non apre "
         "(nota 1 della revisione)", pr_b.get("_stato") == 409 and r.get("ok") is False
         and r["conferma"] == TS.ATTIVITA_PROVA, f"{pr_b} {r}")
st.dati.scrivi("UPDATE studio_prove SET stato = 'consegnata'")
# I file cambiati dopo il caricamento
lib2 = I.Libreria.carica(cartella_app=None)
app = lib2.app["chimica-atomo-app"]
app.cartella = cart / "atomo"
st._libreria_caricata = lib2
r = chiama(ctx_di(LEO), attivita="costruisci l'atomo")
verifica("i file cambiati dopo il caricamento: non la apre", r.get("ok") is False
         and "cambiati" in r["conferma"], str(r))
st._libreria_caricata = None
# La scheda della libreria dice le sue attività; le proposte il tipo
sch = st.scheda_libreria(LEO, vid, "chimica-atomo")
prop = st.proposte_libreria(LEO, vid)["proposte"]
verifica("la scheda e le proposte: l'attività col suo tipo",
         sch["attivita"] == [{"id": "chimica-atomo-app", "titolo": "Costruisci l'atomo",
                              "tipo_app": "esplora", "durata": 10}]
         and any(x["contenuto"] == "chimica-atomo-app" and x["tipo_app"] == "esplora"
                 for x in prop), str(sch.get("attivita")))

# ═══════ revisione della PR #366: la prova che parte, il tempo dei giochi, gli orari, il registro ═══════
print("— la prova che parte, il tempo dei giochi, gli orari")
import calliope.main as MAIN  # noqa: E402
from calliope import minori  # noqa: E402
from calliope.estensioni import manifesto as MF  # noqa: E402

MAIN._lega_studio_giochi(types.SimpleNamespace(studio=st, giochi=hub.giochi))
verifica("Studio e giochi legati come all'avvio (una volta sola)",
         hub.giochi.studio is st and st.ganci_prova == [hub.giochi.ferma_libreria])
MAIN._lega_studio_giochi(types.SimpleNamespace(studio=st, giochi=hub.giochi))
verifica("legarli due volte non raddoppia i ganci", len(st.ganci_prova) == 1)
hub.giochi.partite.clear()
r = chiama(ctx_di(LEO), attivita="osmosi")
pa = next(iter(hub.giochi.partite.values()))
posto = next(iter(pa.posti.values()))
verifica("solo studio_attivita mette il segno «libreria» sulla partita", pa.libreria is True)
pc = st.crea_verifica(LEO, "Biologia", "2026-11-09")
ac = st.aggiungi_argomento(LEO, pc, "La membrana", [], proposto=False)
st.conferma_argomenti(LEO, pc)
for i in range(3):
    st.aggiungi_domanda(LEO, pc, "vero_falso", f"La membrana {i}?", "vero", argomento=ac)
hub.eventi.clear()
st.inizia_prova(LEO, pc)
verifica("una prova che parte chiude subito l'attività aperta dalla persona (nota 1)",
         posto.fermato and any(e[1] == "gioco" and e[2].get("tipo") == "fine_tempo"
                               and "prova aperta" in e[2]["dati"]["nota"] for e in hub.eventi),
         str(hub.eventi)[:300])
st.dati.scrivi("UPDATE studio_prove SET stato = 'consegnata'")


class Minore:
    """Leo minore, col tempo dei giochi finito e (a richiesta) fuori orario."""
    def __init__(self):
        self.vecchi = {k: getattr(minori, k) for k in ("e_minore", "gioco_restante_s",
                                                      "fuori_orario", "tempo_gioco", "profilo")}
        self.fuori = None
        self.contati = []

    def __enter__(self):
        minori.e_minore = lambda prof: getattr(prof, "id", None) == "l1"
        minori.gioco_restante_s = lambda prof: 0
        minori.fuori_orario = lambda prof, adesso=None: self.fuori
        minori.profilo = lambda ctx: LEO
        conta = self.contati
        minori.tempo_gioco = lambda: types.SimpleNamespace(aggiungi=lambda pid, s: conta.append(s))
        return self

    def __exit__(self, *a):
        for k, v in self.vecchi.items():
            setattr(minori, k, v)


hub.giochi.partite.clear()
with Minore() as mn:
    vecchio = hub.giochi.avvia(ctx_di(LEO), "tris", 1, {"titolo": "Tris", "scheda": {
        "macchina": {"inizio": "t", "fasi": {"t": {"comandi": {}}}}}}, {})
    verifica("contrario: un gioco dell'archivio col tempo dei giochi finito non si apre",
             "tempo dei giochi" in str(vecchio.get("conferma", "")), str(vecchio)[:200])
    r = chiama(ctx_di(LEO), attivita="accendi i bit")
    pa = next((x for x in hub.giochi.partite.values() if x.nome == "libreria_bit"), None)
    verifica("col tempo dei giochi finito la mini-app si apre: è studio (decisione del 31/10)",
             r.get("ok") is not False and pa is not None and pa.libreria, str(r)[:200])
    posto = next(iter(pa.posti.values())) if pa else None
    rb = hub.giochi._t_battito(pa, posto, {"secondi": 15}) if posto else {}
    verifica("il battito di una mini-app non conta nel tempo dei giochi",
             rb.get("ok") and not rb.get("fine_tempo") and not mn.contati, str(rb))
    # Aperta alle 21:59, alle 22:00 comincia il riposo: al battito si chiude
    mn.fuori = "22:00-07:00"
    posto.ultimo_battito = 0
    hub.eventi.clear()
    rb = hub.giochi._t_battito(pa, posto, {"secondi": 15})
    verifica("aperta prima del riposo, al fuori orario si chiude (al battito, con la nota)",
             rb.get("fine_tempo") and posto.fermato and any(
                 e[2].get("tipo") == "fine_tempo" and "riposare" in e[2]["dati"]["nota"]
                 for e in hub.eventi), str(rb))
    r = chiama(ctx_di(LEO), attivita="accendi i bit")
    verifica("fuori orario la mini-app non si apre (anche chiamando il tool)",
             r.get("ok") is False and "riposare" in r["conferma"], str(r)[:200])
# Il registro dell'archivio e il prefisso riservato
righe_arch = []
est_finta = types.SimpleNamespace(archivio=types.SimpleNamespace(registra=righe_arch.append))
gio2 = Giochi(cfg, hub, est_finta, log=lambda *a: None)
mitt = Mittente(persona="l1", nome="Leo", livello="familiare", certo=True)
from calliope.schermi.giochi import Partita  # noqa: E402
gio2._registra(Partita("libreria_bit", 0, {"titolo": "Accendi i bit"}, mitt, libreria=True), "avvio")
gio2._registra(Partita("tris", 1, {"titolo": "Tris"}, mitt), "avvio")
verifica("le partite della libreria non vanno nel registro dell'archivio delle estensioni (nota 3)",
         [x["gioco"] for x in righe_arch] == ["tris"], str(righe_arch))
man = json.loads((MA.CARTELLA / "atomo" / "manifesto.json").read_text("utf-8"))
try:
    MF.valida(man)
    riservato = False
except MF.ManifestoNonValido as ex:
    riservato = "riservato" in str(ex)
verifica("il prefisso «libreria_» è riservato: un'estensione dell'archivio non lo usa (nota 3)",
         riservato and MF.valida(man, riservato=True)["nome"] == "libreria_atomo")

# Attraverso Brain
print("— attraverso Brain")
import prova_politica as PP  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402

regb = build_registry()
for sp in TS.studio_specs():
    regb.register(sp)
cb = ctx_di(LEO)
for kk, vv in (("from_session", False), ("voce_sicura", "Leo"), ("punteggio", 0.7),
               ("conferma_breve", False), ("sfida", None), ("sfida_superata", False)):
    setattr(cb.speaker_ctx, kk, vv)
b = Brain(cfg, regb, cb)
b.backend = PP.Copione()
b.backend.risposte = [PP.chiama("studio_attivita", {"attivita": "accendi i bit"}),
                      PP.testo("Eccola.")]
prima = len(hub.giochi.partite)
with contextlib.redirect_stdout(io.StringIO()):
    "".join(b.stream_reply("Calliope, fammi giocare con i bit", "familiare"))
verifica("Brain: «fammi giocare con i bit» apre «Accendi i bit» senza domande",
         b.last_tools and b.last_tools[0]["nome"] == "studio_attivita" and b.last_tools[0]["ok"]
         and len(hub.giochi.partite) == prima + 1
         and any(x.nome == "libreria_bit" for x in hub.giochi.partite.values()),
         str(b.last_tools)[:300])
st.close()
shutil.rmtree(TMP, ignore_errors=True)
print("\nTutto bene." if not errori else f"\n{errori} prove non riuscite.")
sys.exit(1 if errori else 0)
