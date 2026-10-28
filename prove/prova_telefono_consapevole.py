import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""
Prova a secco: quello che Calliope dice del telefono e dello schermo personale (28/10/2026, issue
#288, #289, #290 e #291, epic #251).

Casi veri della DGX del 28/10 (versione 0fbda07), dal telefono, con nomi di fantasia:
- 13:53 «Apri lo schermo dei documenti su questo dispositivo.» → «non posso aprire uno schermo
  perché non è un computer», e l'offerta del portatile, che non era collegato;
- 13:54 «la scheda documenti del tab Le mie cose» → «non ho una scheda Le mie cose su questo
  dispositivo».
La nota del dispositivo diceva «il telefono, non un computer» e «niente webcam né schermo del
computer»; Le mie cose compariva solo dentro le frasi dei tool.

1. #288 — la nota del dispositivo con lo schermo personale (aperto, chiuso, assente; ospite e zona
   grigia mai; Casa nascosta sotto i 13 anni, Ufficio per chi non amministra), lo scritto dallo
   schermo personale; il paragrafo delle sezioni nel prompt di sistema (stima dei token) e il
   prefisso uguale fra turni con lo schermo aperto e chiuso, un adulto e un minore; i due casi
   del 28/10 nel Brain: nota e prompt che arrivano al modello, e schermo_mostra con la pagina;
   il campo `dispositivo` del registro dei turni;
2. #289 — schermo_mostra con cosa=pagina: aperto (la pagina si sposta), chiuso («Lo trovi in Le
   mie cose…»), assente, ospite, zona grigia, Ufficio solo per chi amministra e mai a un minore,
   pagina sconosciuta, forme della pagina; classe sicura nella politica, fuori dai tocchi;
3. #290 — i risultati dei lavori rimasti in casa: Le mie cose › Lavori e programmi con lo schermo
   abbinato (aperto o chiuso), la cartella senza «server» né «satellite» senza schermo; la frase
   della consegna; la descrizione di documento_crea;
4. #291 — la versione del protocollo e della pagina nella riga «[SATELLITE] collegato», sul server
   vero; una versione della pagina fuori forma non entra nei log.
"""

import datetime
import json
import shutil
import tempfile
import time
import types
from pathlib import Path

from calliope import dispositivo
from calliope.brain import CHARS_PER_TOKEN, Brain
from calliope.config import Config
from calliope.schermi.hub import mittente_da
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

ERRORI = []
TMP = Path(tempfile.mkdtemp(prefix="calliope-consapevole-"))


def verifica(nome, ok, dettaglio=""):
    print(f"  {'ok ' if ok else 'NO '} {nome}" + ("" if ok else f"  → {dettaglio}"))
    if not ok:
        ERRORI.append(nome)


class Prof:
    def __init__(self, pid, name, admin=False, nascita=None):
        self.id, self.name, self.admin, self.nascita = pid, name, admin, nascita
        self.gender, self.preferred_voice, self.giovane, self.tono = "m", None, False, None
        self.fascia, self.preferred_tone = None, None


NASCITA_10 = (datetime.date.today().replace(day=1) - datetime.timedelta(days=365 * 10 + 40)).isoformat()


class Speakers:
    def __init__(self):
        self.p = {"Dario": Prof("dario", "Dario", admin=True), "Bianca": Prof("bianca", "Bianca"),
                  "Ada": Prof("ada", "Ada", nascita=NASCITA_10)}

    def get(self, n):
        return self.p.get(n)

    def by_id(self, i):
        return next((p for p in self.p.values() if p.id == i), None)

    def known_speakers(self):
        return list(self.p)


class SC:
    def __init__(self, nome="Dario", livello="amministra", come="voce", sessione=False):
        self.current_speaker, self.current_level = nome, livello
        self.identified_by, self.from_session, self.sfida = come, sessione, None


class Hub:
    """Gli schermi finti: gli abbinati con il proprietario, quelli con la pagina aperta, le pagine
    aperte da apri_pagina (come Schermi._a_personali: solo le aperte ricevono)."""
    url = "https://calliope.casa:8766"

    def __init__(self, abbinati=(), aperti=()):
        self._abb = [{"id": i, "proprietario": p, "personale": True} for i, p in abbinati]
        self.aperti = set(aperti)
        self.pagine = []

    def mittente(self, ctx):
        return mittente_da(ctx)

    def abbinati(self):
        return list(self._abb)

    def schermo(self, sid):
        return next((s for s in self._abb if s["id"] == sid), None)

    def collegato(self, sid, locale=None):
        return sid in self.aperti

    def personale_collegato(self, m):
        return bool(m.certo and m.persona) and any(
            s["proprietario"] == m.persona and s["id"] in self.aperti for s in self._abb)

    def personale_abbinato(self, m):
        return bool(m.certo and m.persona) and any(s["proprietario"] == m.persona for s in self._abb)

    def apri_pagina(self, persona, pagina):
        n = sum(1 for s in self._abb if s["proprietario"] == persona and s["id"] in self.aperti)
        if n:
            self.pagine.append((persona, pagina))
        return n

    def invia(self, card, sender, forza=False):
        return {"schermi": [], "destinatari": [], "motivo": "nessuno_schermo"}


def contesto(hub, sc, cfg=None):
    cfg = cfg or Config()
    return ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=sc, speaker=None, schermi=hub)


# ─────────────────────────── 1. #288: la nota e il prompt ───────────────────────────

def prova_nota():
    print("── 1. #288: la nota del dispositivo con lo schermo personale ──")
    tel = dispositivo.descrivi("telefono")
    aperto = Hub(abbinati=[(1, "dario")], aperti=[1])
    chiuso = Hub(abbinati=[(1, "dario")])
    s = dispositivo.schermo_di(contesto(aperto, SC()))
    verifica("schermo di chi amministra aperto: «aperto», niente nascosto", s == {"stato": "aperto", "nascoste": []}, s)
    n = dispositivo.nota(tel, None, True, s)
    verifica("caso 13:53: «il telefono, non un computer; lo schermo personale di chi parla è aperto adesso»",
             n == "dispositivo: il telefono, non un computer; lo schermo personale di chi parla è aperto "
                  "adesso; nessun computer collegato, quindi niente webcam né schermata del computer.", n)
    verifica("il «niente» è della webcam e della schermata del computer, mai dello schermo",
             "niente webcam né schermo" not in n and "schermata del computer" in n, n)
    s = dispositivo.schermo_di(contesto(chiuso, SC()))
    n = dispositivo.nota(tel, None, True, s)
    verifica("schermo abbinato ma chiuso: «è chiuso adesso»", s["stato"] == "chiuso"
             and "lo schermo personale di chi parla è chiuso adesso" in n, n)
    s = dispositivo.schermo_di(contesto(Hub(), SC()))
    n = dispositivo.nota(tel, None, True, s)
    verifica("nessuno schermo abbinato: «chi parla non ha uno schermo personale»",
             s["stato"] == "nessuno" and "chi parla non ha uno schermo personale" in n, n)
    s = dispositivo.schermo_di(contesto(aperto, SC(None, "ospite", None)))
    verifica("contrario: un ospite non ha schermo personale (anche col telefono di Dario aperto)",
             s["stato"] == "nessuno", s)
    s = dispositivo.schermo_di(contesto(aperto, SC(come="conversazione", sessione=True)))
    verifica("contrario: zona grigia, nessuno schermo personale", s["stato"] == "nessuno", s)
    verifica("contrario: senza schermi nessuna riga sullo schermo",
             dispositivo.schermo_di(contesto(None, SC())) is None
             and dispositivo.nota(tel, None, True, None) == "dispositivo: il telefono, non un computer; "
             "nessun computer collegato, quindi niente webcam né schermata del computer.")
    # Permessi ed età: Ufficio per chi non amministra, Casa sotto i 13 anni
    h = Hub(abbinati=[(1, "dario"), (2, "bianca"), (3, "ada")], aperti=[1, 2, 3])
    s = dispositivo.schermo_di(contesto(h, SC()), ufficio=True)
    verifica("chi amministra con l'Ufficio: niente nascosto", s["nascoste"] == [], s)
    s = dispositivo.schermo_di(contesto(h, SC("Bianca", "familiare")), ufficio=True)
    n = dispositivo.nota(tel, None, True, s)
    verifica("un familiare con l'Ufficio installato: «e lì non c'è Ufficio»",
             s["nascoste"] == ["Ufficio"] and "aperto adesso e lì non c'è Ufficio" in n, n)
    s = dispositivo.schermo_di(contesto(h, SC("Bianca", "familiare")), ufficio=False)
    verifica("senza l'Ufficio installato non se ne parla", s["nascoste"] == [], s)
    s = dispositivo.schermo_di(contesto(h, SC("Ada", "familiare")), ufficio=True)
    n = dispositivo.nota(tel, None, True, s)
    verifica("una bambina di 10 anni: «lì non ci sono Casa e Ufficio»",
             s["nascoste"] == ["Casa", "Ufficio"] and "lì non ci sono Casa e Ufficio" in n, n)
    # Lo scritto dallo schermo personale (il PC o il telefono)
    n = dispositivo.nota(dispositivo.descrivi("scritto", personale=True), "portatile", True,
                         {"stato": "aperto", "nascoste": []})
    verifica("scritto dallo schermo personale: «lo schermo personale a sezioni di chi parla, per scritto»",
             n.startswith("dispositivo: lo schermo personale a sezioni di chi parla, per scritto;")
             and "aperto adesso" not in n and "non un computer" not in n, n)
    verifica("scritto da uno schermo di stanza: come prima",
             dispositivo.descrivi("scritto") == {"canale": "scritto", "pc_qui": False})
    n = dispositivo.nota(dispositivo.descrivi("satellite", True), "portatile", True,
                         {"stato": "aperto", "nascoste": []})
    verifica("dal portatile: un computer, e lo schermo personale aperto",
             n == "dispositivo: il portatile, un computer; lo schermo personale di chi parla è aperto adesso.", n)
    # Il ciclo: lo scritto dallo schermo personale
    from calliope.ciclo import Ciclo
    finto = types.SimpleNamespace(s=types.SimpleNamespace(schermi=h, satelliti=None), listener=None,
                                  corsia=types.SimpleNamespace(satellite_id=None))
    d = Ciclo._dispositivo_turno(finto, types.SimpleNamespace(scritto={"tipo": "scritto", "schermo_id": 1}))
    verifica("ciclo: scritto dallo schermo personale → personale", d and d.get("personale") is True, d)
    h2 = Hub()
    h2._abb = [{"id": 9, "proprietario": None}]
    finto.s.schermi = h2
    d = Ciclo._dispositivo_turno(finto, types.SimpleNamespace(scritto={"tipo": "scritto", "schermo_id": 9}))
    verifica("ciclo: scritto da uno schermo di stanza → non personale", d == {"canale": "scritto", "pc_qui": False}, d)


class Backend:
    def __init__(self, copione):
        self.copione, self.visti, self.strumenti = list(copione), [], []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        self.strumenti.append(tools)
        yield from self.copione.pop(0)


def brain(copione, hub, sc, **reg):
    cfg = Config()
    cfg.storia_inattiva_s = 0
    ctx = contesto(hub, sc, cfg)
    b = Brain(cfg, build_registry(schermi=True, **reg), ctx)
    b.backend = Backend(copione)
    return b


def dati(req):
    return next((m["content"] for m in req if m["role"] == "system"
                 and m["content"].startswith("Dati del turno")), "")


def prova_prompt():
    print("── 1. #288: il prompt di sistema e i due casi del 28/10 ──")
    cfg = Config()
    paragrafo = cfg._frase_sezioni(False)
    con = cfg.prompt_for(True, schermi=True, sezioni=True)
    senza = cfg.prompt_for(True, schermi=True)
    verifica("prompt: il paragrafo c'è con gli schermi personali", paragrafo in con and paragrafo not in senza)
    verifica("prompt: sezioni, pagine, cosa si fa dallo schermo, foto per 60 giorni e «archiviala»",
             all(x in paragrafo for x in ("Adesso, Conversazione, Le mie cose, Casa e Io", "Lavori e programmi",
                                          "Cassetto, Documenti, Giochi", "cominciata a voce", "spuntano le liste",
                                          "«+1 minuto» e «Ferma»", "60 giorni", "«archiviala»",
                                          "schermo_mostra con cosa=pagina",
                                          "«in Le mie cose, alla voce Documenti»", "sotto i 13 anni")), paragrafo)
    verifica("prompt: Ufficio solo con l'ufficio installato, e solo per chi amministra",
             "Ufficio" not in paragrafo and "e, solo per chi amministra, Ufficio" in cfg._frase_sezioni(True))
    verifica("contrario: senza schermi il paragrafo non c'è (anche con sezioni)",
             "Le mie cose" not in cfg.prompt_for(True, sezioni=True))
    cfg2 = Config()
    cfg2.immagini_tenuta = False
    verifica("con immagini_tenuta spenta: foto e file per i giorni del cassetto",
             "foto e file restano nel Cassetto 7 giorni" in cfg2._frase_sezioni(False), cfg2._frase_sezioni(False))
    tok = round(len(cfg._frase_sezioni(True)) / CHARS_PER_TOKEN)
    print(f"     (paragrafo: {len(cfg._frase_sezioni(True))} caratteri, ~{tok} token stimati a "
          f"{CHARS_PER_TOKEN} caratteri per token)")
    verifica("stima dei token del paragrafo sotto 240", tok < 240, tok)

    # I due casi del 28/10 nel Brain, dal telefono con lo schermo di Dario aperto
    hub = Hub(abbinati=[(1, "dario")], aperti=[1])
    chiama = [("calls", [{"id": "c1", "name": "schermo_mostra",
                          "arguments": {"cosa": "pagina", "pagina": "documenti"}}])]
    # La frase è pronta (risposta_finale): niente seconda passata
    b = brain([chiama, chiama], hub, SC())
    b.dispositivo_turno = dispositivo.descrivi("telefono")
    detto = "".join(b.stream_reply("Apri lo schermo dei documenti su questo dispositivo.", "amministra"))
    req = b.backend.visti[0]
    sistema = req[0]["content"]
    d = dati(req)
    verifica("13:53: il prompt che arriva al modello ha le sezioni e cosa=pagina",
             paragrafo in sistema, sistema[-900:])
    verifica("13:53: la nota dice lo schermo personale aperto, senza «niente … schermo del computer»",
             "lo schermo personale di chi parla è aperto adesso" in d and "schermo del computer" not in d, d)
    tool = next((t for t in b.backend.strumenti[0] if t["function"]["name"] == "schermo_mostra"), None)
    props = (tool or {}).get("function", {}).get("parameters", {}).get("properties", {})
    verifica("13:53: schermo_mostra ha cosa=pagina e il parametro pagina",
             "pagina" in props.get("cosa", {}).get("enum", []) and "documenti" in props.get("pagina", {}).get("enum", []),
             props)
    verifica("13:53: la pagina Documenti si apre sullo schermo di Dario e la frase lo dice",
             hub.pagine == [("dario", "documenti")] and "Le mie cose, alla voce Documenti" in detto
             and "computer" not in detto and "portatile" not in detto, (hub.pagine, detto))
    verifica("13:53: il registro dei turni avrà dispositivo telefono e schermo aperto",
             b.last_dispositivo == {"canale": "telefono", "schermo": "aperto"}, b.last_dispositivo)
    b.dispositivo_turno = dispositivo.descrivi("telefono")
    hub.aperti.clear()
    detto2 = "".join(b.stream_reply("La scheda documenti del tab Le mie cose.", "amministra"))
    req2 = b.backend.visti[1]
    verifica("13:54 (schermo chiuso): «Lo trovi in Le mie cose, alla voce Documenti»",
             "Lo trovi in Le mie cose, alla voce Documenti" in detto2 and "portatile" not in detto2, detto2)
    verifica("13:54: la nota dice lo schermo chiuso", "chiuso adesso" in dati(req2), dati(req2))
    verifica("prefisso: prompt di sistema e tool uguali con lo schermo aperto e chiuso",
             req2[0] == req[0] and b.backend.strumenti[1] == b.backend.strumenti[0])
    # Un altro che parla (un familiare, poi una bambina): il prefisso resta quello
    for nome in ("Bianca", "Ada"):
        b2 = brain([[("text", "Ok.")]], Hub(abbinati=[(1, nome.lower())], aperti=[1]),
                   SC(nome, "familiare"))
        b2.dispositivo_turno = dispositivo.descrivi("telefono")
        "".join(b2.stream_reply("Cosa c'è in Le mie cose?", "familiare"))
        verifica(f"prefisso: uguale anche per {nome} (il prompt non dipende da chi parla)",
                 b2.backend.visti[0][0] == req[0], b2.backend.visti[0][0]["content"][-200:])
    verifica("…e per Ada la nota dice Casa nascosta", "lì non c'è Casa" in dati(b2.backend.visti[0]),
             dati(b2.backend.visti[0]))
    # Il registro dei turni: il campo dispositivo dal Brain (Ciclo copia last_dispositivo)
    from calliope.ciclo import Ciclo
    src = Path(sys.modules[Ciclo.__module__].__file__).read_text(encoding="utf-8")
    verifica("registro dei turni: il ciclo scrive il campo «dispositivo»",
             'self.rec["dispositivo"]' in src and "last_dispositivo" in src)


# ─────────────────────────── 2. #289: schermo_mostra con la pagina ───────────────────────────

def prova_pagina():
    print("── 2. #289: schermo_mostra con cosa=pagina ──")
    reg = build_registry(schermi=True)

    def call(args, hub, sc, livello=None):
        ctx = contesto(hub, sc)
        ctx.regole = []
        r = json.loads(reg.call("schermo_mostra", args, ctx, livello or sc.current_level))
        return r, ctx

    h = Hub(abbinati=[(1, "dario"), (2, "bianca"), (3, "ada")], aperti=[1, 2, 3])
    r, ctx = call({"cosa": "pagina", "pagina": "documenti"}, h, SC())
    verifica("aperto: la pagina Documenti sullo schermo di chi parla, «Ecco…»",
             r.get("ok") and h.pagine[-1] == ("dario", "documenti")
             and r["risposta_finale"] == "Ecco, sul tuo schermo c'è Le mie cose, alla voce Documenti."
             and "schermo_pagina" in ctx.regole, r)
    for detto, attesa in (("lavori e programmi", "lavori"), ("Liste", "liste"), ("agenda", "agenda"),
                          ("cassetto", "cassetto"), ("giochi", "giochi")):
        r, _ = call({"cosa": "pagina", "pagina": detto}, h, SC())
        verifica(f"la pagina «{detto}» → #/cose/{attesa}", h.pagine[-1] == ("dario", attesa), (h.pagine[-1:], r))
    r, _ = call({"cosa": "pagina", "pagina": "ufficio"}, h, SC())
    verifica("Ufficio: chi amministra sì", h.pagine[-1] == ("dario", "ufficio"), r)
    n = len(h.pagine)
    r, _ = call({"cosa": "pagina", "pagina": "ufficio"}, h, SC("Bianca", "familiare"))
    verifica("Ufficio: un familiare no, e niente si sposta", not r.get("ok") and len(h.pagine) == n
             and "non c'è" in r["risposta_finale"], r)
    r, _ = call({"cosa": "pagina", "pagina": "ufficio"}, h, SC("Ada", "familiare"))
    verifica("Ufficio: una bambina no", not r.get("ok") and len(h.pagine) == n, r)
    r, _ = call({"cosa": "pagina", "pagina": "documenti"}, h, SC("Ada", "familiare"))
    verifica("una bambina: Documenti sì (la pagina c'è anche per lei)", h.pagine[-1] == ("ada", "documenti"), r)
    n = len(h.pagine)
    r, _ = call({"cosa": "pagina", "pagina": "documenti"}, h, SC(None, "ospite", None))
    verifica("ospite: niente, solo per chi è riconosciuto dalla voce", not r.get("ok") and len(h.pagine) == n
             and "riconosco dalla voce" in r["risposta_finale"], r)
    r, _ = call({"cosa": "pagina", "pagina": "documenti"}, h, SC(come="conversazione", sessione=True))
    verifica("zona grigia: niente", not r.get("ok") and len(h.pagine) == n, r)
    r, ctx = call({"cosa": "pagina", "pagina": "documenti"}, Hub(abbinati=[(1, "dario")]), SC())
    verifica("chiuso: «Lo trovi in Le mie cose, alla voce Documenti», niente mandato",
             r["risposta_finale"].startswith("Lo trovi in Le mie cose, alla voce Documenti")
             and "schermo_pagina_chiuso" in ctx.regole, r)
    r, _ = call({"cosa": "pagina", "pagina": "documenti"}, Hub(), SC())
    verifica("assente: non ne hai uno abbinato", not r.get("ok") and "non ne hai uno" in r["risposta_finale"], r)
    r, _ = call({"cosa": "pagina", "pagina": "rubrica segreta"}, h, SC())
    verifica("pagina sconosciuta: chiede quale, niente si sposta", not r.get("ok") and len(h.pagine) == n
             and r["risposta_finale"].startswith("Quale pagina"), r)
    r, _ = call({"cosa": "pagina"}, h, SC())
    verifica("cosa=pagina senza pagina: chiede quale", r["risposta_finale"].startswith("Quale pagina"), r)
    from calliope.politica import CLASSI, SICURO
    from calliope.schermi.tocchi import TOCCABILI
    verifica("politica: schermo_mostra resta di classe sicura (cambia solo la vista)",
             CLASSI["schermo_mostra"].classe == SICURO, CLASSI["schermo_mostra"])
    verifica("tocchi: schermo_mostra non è un tocco della pagina", "schermo_mostra" not in TOCCABILI)
    spec = reg.get("schermo_mostra")
    verifica("descrizione: «uno schermo, anche il telefono di chi parla»",
             "anche il telefono di chi parla" in spec.description and "schermo di casa" not in spec.description,
             spec.description[:120])
    # Il server degli schermi vero: solo un nome di raccolta, solo alle pagine del proprietario
    from calliope.schermi import ArchivioSchermi, Schermi
    cfg = Config()
    cfg.memory_db = str(TMP / "schermi.db")
    vero = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    mandati = []
    vero._a_personali = lambda persona, tipo, msg: mandati.append((persona, tipo, msg)) or 1
    verifica("Schermi.apri_pagina: l'evento «pagina» col solo nome",
             vero.apri_pagina("dario", "documenti") == 1
             and mandati == [("dario", "pagina", json.dumps({"pagina": "documenti"}))], mandati)
    verifica("Schermi.apri_pagina: un indirizzo o un nome fuori forma non parte",
             vero.apri_pagina("dario", "../io") == 0 and vero.apri_pagina("dario", "cose/x") == 0
             and vero.apri_pagina(None, "liste") == 0 and len(mandati) == 1, mandati)


# ─────────────────────────── 3. #290: le frasi ───────────────────────────

def prova_frasi():
    print("── 3. #290: le frasi senza «server» né «satellite» ──")
    from calliope.agenti.ciclo import Lavoro
    from calliope.agenti.servizio import Lavori
    from calliope.documenti.consegna import LocalDelivery, RemoteDelivery
    from calliope.tools.agenti import _schermo

    class SrvSenzaFile:
        def __init__(self, c):
            self.c = c

        def per_pc(self):
            return self.c

    # La consegna dei documenti: assente e telefono senza file
    d = RemoteDelivery(SrvSenzaFile(None), LocalDelivery(TMP / "riserva"), "portatile").deliver("A", "pdf", b"%PDF")
    verifica("consegna, portatile non collegato: «tra i miei documenti, perché il portatile non è collegato»",
             d["dove"] == "tra i miei documenti, perché il portatile non è collegato", d["dove"])
    tel = types.SimpleNamespace(esecutore=None)
    d = RemoteDelivery(SrvSenzaFile(tel), LocalDelivery(TMP / "riserva"), "portatile").deliver("B", "pdf", b"%PDF")
    verifica("consegna dal telefono: senza «server» né «satellite»",
             "server" not in d["dove"] and "satellite" not in d["dove"] and "non riceve file" in d["dove"], d["dove"])

    # I lavori dell'agente: la scelta dei documenti (schermo aperto, chiuso, assente)
    def finto_lav(hub, sc):
        lav = Lavoro("l1", "ricerca", "le api", persona="dario", persona_nome="Dario", titolo="Le api")
        _schermo(contesto(hub, sc), lav)
        return lav
    dest = TMP / "lavoro"
    dest.mkdir(exist_ok=True)
    (dest / "risultato.md").write_text("# Le api", encoding="utf-8")
    for nome, hub, attesa in (
            ("aperto", Hub(abbinati=[(1, "dario")], aperti=[1]), "in Le mie cose, alla voce Lavori e programmi"),
            ("chiuso", Hub(abbinati=[(1, "dario")]), "in Le mie cose, alla voce Lavori e programmi"),
            ("assente", Hub(), "tra i miei file, nella cartella Lavori, perché il dispositivo da cui mi parli "
                                "non riceve file")):
        hub.automatiche = True
        lav = finto_lav(hub, SC())
        self = types.SimpleNamespace(consegna=types.SimpleNamespace(nome="portatile", server=SrvSenzaFile(tel)),
                                     log=lambda m: None, _dove_in_casa=Lavori._dove_in_casa)
        ris = {"file": ["risultato.md"]}
        Lavori._consegna_risultato(self, lav, ris, dest)
        verifica(f"lavoro rimasto in casa, schermo {nome}: «{attesa}»", ris.get("dove") == attesa
                 and "server" not in ris["dove"] and "satellite" not in ris["dove"], ris.get("dove"))
    lav = finto_lav(Hub(abbinati=[(1, "dario")]), SC(None, "ospite", None))
    verifica("lavoro di un ospite: la cartella (niente pagina)",
             Lavori._dove_in_casa(lav, "x").startswith("tra i miei file"))
    rotto = Lavoro("l2", "ricerca", "x")
    rotto.ha_pagina = lambda: 1 / 0
    verifica("contrario: ha_pagina guasta → la cartella", Lavori._dove_in_casa(rotto, "x").startswith("tra i miei file"))
    from calliope.tools.documenti import documenti_specs
    spec = next(s for s in documenti_specs(["word", "pdf"]) if s.name == "documento_crea")
    verifica("documento_crea: «lo consegna a chi parla», non «lo salva sul PC»",
             "lo consegna a chi parla" in spec.description and "salva sul PC" not in spec.description,
             spec.description[:100])
    # Nessuna frase rivolta all'utente con «sul server» nel codice che parla dei documenti
    import re
    for f in ("calliope/documenti/consegna.py", "calliope/agenti/servizio.py", "calliope/tools/casa.py"):
        testo = (Path(__file__).resolve().parent.parent / f).read_text(encoding="utf-8")
        frasi = [m.group(0) for m in re.finditer(r'f?"[^"\n]*sul server[^"\n]*"', testo)
                 if not m.group(0).lstrip("f\"").startswith("#")]
        verifica(f"{f}: nessuna stringa con «sul server»", not frasi, frasi[:3])


# ─────────────────────────── 4. #291: le versioni nei log ───────────────────────────

def prova_versioni():
    print("── 4. #291: protocollo e pagina nella riga «collegato» ──")
    from websockets.sync.client import connect
    from calliope.satellite import protocollo as P
    from calliope.satellite.archivio import ArchivioSatelliti
    from calliope.satellite.server import ServerSatelliti
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "sat.db")
    cfg.satellite_porta = 0
    righe = []
    arch = ArchivioSatelliti(cfg.memory_db)
    srv = ServerSatelliti(cfg, arch, log=righe.append).avvia()
    srv.avviato.set()
    try:
        _, token = arch.crea_con_token("telefono")
        url = f"ws://127.0.0.1:{srv.port}{P.PERCORSO_AUDIO}"
        for pagina in ("calliope-telefono-pagina-v19", "<script>v99</script>"):
            prima = sum("[SATELLITE] collegato" in r for r in righe)
            with connect(url, compression=None) as ws:
                ws.send(P.testo(tipo="ciao", versione=P.VERSIONE, token=token, primo=False,
                                nome="telefono", pagina=pagina))
                ws.recv(timeout=10)
                fine = time.monotonic() + 5
                while (time.monotonic() < fine
                       and sum("[SATELLITE] collegato" in r for r in righe) == prima):
                    time.sleep(0.05)
            time.sleep(0.3)
        coll = [r for r in righe if "[SATELLITE] collegato" in r]
        verifica("riga «collegato»: protocollo e pagina del telefono",
                 coll and f"protocollo {P.VERSIONE}" in coll[0] and "pagina calliope-telefono-pagina-v19" in coll[0],
                 coll[:1])
        verifica("contrario: una versione della pagina fuori forma non entra nei log",
                 len(coll) >= 2 and "script" not in coll[1] and "pagina " not in coll[1]
                 and f"protocollo {P.VERSIONE}" in coll[1], coll[1:2])
    finally:
        srv.ferma()
        arch.close()
    js = (Path(__file__).resolve().parent.parent / "calliope/schermi/pagina/telefono/telefono.js").read_text(encoding="utf-8")
    sw = (Path(__file__).resolve().parent.parent / "calliope/schermi/pagina/telefono/sw.js").read_text(encoding="utf-8")
    verifica("il telefono manda nel «ciao» la cache del service worker (calliope-telefono-pagina-vN)",
             "pagina: st.pagina" in js and "calliope-telefono-pagina-v" in js
             and re.search(r'const CACHE = "calliope-telefono-pagina-v\d+";', sw) is not None)


import re  # noqa: E402 — usato in prova_versioni


def main() -> int:
    try:
        prova_nota()
        prova_prompt()
        prova_pagina()
        prova_frasi()
        prova_versioni()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
