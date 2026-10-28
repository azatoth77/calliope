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
    def __init__(self, nome="Dario", livello="amministra", come="voce", sessione=False, **dubbi):
        self.current_speaker, self.current_level = nome, livello
        self.identified_by, self.from_session, self.sfida = come, sessione, None
        # I segni del ciclo per la voce incerta con un minore (ciclo.py, voce_proprietario,
        # minore_piu_protetto, amministra_minore_vicino)
        self.minore_incerto = dubbi.get("minore_incerto")
        self.incerta = dubbi.get("incerta")
        self.minore_vicino = dubbi.get("minore_vicino")


# Seconda revisione della PR #294: dal telefono di Dario con un minore possibile
def VOCE_PROPRIETARIO():
    """voce incerta fra Dario e Ada, vale Dario dalla sua conversazione (ciclo.py)."""
    return SC("Dario", "familiare", come="conversazione", sessione=True,
              minore_incerto="Ada", incerta=("Dario", "Ada"))


def MINORE_VICINO():
    """la voce è di Dario, ma Ada ha parlato vicino da poco: familiare, dalla conversazione."""
    return SC("Dario", "familiare", come="voce", sessione=True, minore_vicino="Ada")


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


def contesto(hub, sc, cfg=None, disp=None, ufficio=None):
    cfg = cfg or Config()
    ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=sc, speaker=None, schermi=hub,
                      ufficio=ufficio)
    ctx.dispositivo = disp          # come Brain a ogni turno (revisione della PR #294)
    return ctx


# Il telefono di Dario (satellite personale, «di» = il suo id), da cui parla anche nella zona grigia
TEL_DARIO = dispositivo.descrivi("telefono", di="dario")


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
    n = dispositivo.nota(tel, None, True, s)
    verifica("contrario: un ospite (anche col telefono di Dario aperto): «non è riconosciuto», "
             "mai «non ha uno schermo personale»",
             s["stato"] == "ospite" and "non è riconosciuto dalla voce" in n
             and "non ha uno schermo personale" not in n, n)
    # La zona grigia (revisione della PR #294): frase breve, conferma dentro la conversazione,
    # un minore vicino. Mai «non ha uno schermo personale»
    for come, sc in (("frase breve", SC(come="breve", sessione=True)),
                     ("conversazione", SC(come="conversazione", sessione=True))):
        s = dispositivo.schermo_di(contesto(aperto, sc, disp=TEL_DARIO))
        n = dispositivo.nota(TEL_DARIO, None, True, s)
        verifica(f"zona grigia ({come}) dal suo telefono: lo schermo aperto, vero",
                 s["stato"] == "aperto" and "aperto adesso" in n and "non ha uno schermo" not in n, n)
        s = dispositivo.schermo_di(contesto(aperto, sc, disp=tel))
        n = dispositivo.nota(tel, None, True, s)
        verifica(f"zona grigia ({come}) da un telefono non suo: «non sono sicura di chi parla», "
                 f"mai «non ha uno schermo personale»",
                 s["stato"] == "incerto" and "non sono sicura di chi parla" in n
                 and "non ha uno schermo personale" not in n, n)
    s = dispositivo.schermo_di(contesto(aperto, SC("Ada", "familiare", come="minore_piu_protetto",
                                                   sessione=True, minore_incerto="Ada",
                                                   incerta=("Dario", "Ada")), disp=TEL_DARIO))
    verifica("zona grigia col minore dal telefono di Dario: incerto (il telefono non è di Ada)",
             s["stato"] == "incerto", s)
    for nome, sc in (("voce_proprietario, incerta fra Dario e Ada", VOCE_PROPRIETARIO()),
                     ("minore vicino a Dario", MINORE_VICINO())):
        s = dispositivo.schermo_di(contesto(aperto, sc, disp=TEL_DARIO))
        n = dispositivo.nota(TEL_DARIO, None, True, s)
        verifica(f"dal telefono di Dario, {nome}: «non sono sicura di chi parla», mai «aperto»",
                 s["stato"] == "incerto" and "non sono sicura di chi parla" in n
                 and "aperto adesso" not in n, n)
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
    n2 = dispositivo.nota(dispositivo.descrivi("scritto", personale=True), "portatile", True,
                          {"stato": "aperto", "nascoste": ["Casa", "Ufficio"]})
    verifica("scritto dallo schermo personale di una bambina: anche lì «lì non ci sono Casa e Ufficio»",
             "per scritto; lì non ci sono Casa e Ufficio;" in n2, n2)
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
    verifica("ciclo: scritto dallo schermo personale → personale, di Dario",
             d and d.get("personale") is True and d.get("di") == "dario", d)
    sat = types.SimpleNamespace(per_id=lambda sid: types.SimpleNamespace(
        canale="telefono", esecutore=None, satellite={"proprietario": "dario"}))
    finto_t = types.SimpleNamespace(s=types.SimpleNamespace(schermi=h, satelliti=sat),
                                    listener=types.SimpleNamespace(remoto=True, canale="telefono"),
                                    corsia=types.SimpleNamespace(satellite_id=4))
    d = Ciclo._dispositivo_turno(finto_t, types.SimpleNamespace(scritto=None))
    verifica("ciclo: dal telefono personale di Dario → «di» dario", d and d.get("di") == "dario", d)
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
    # Gli interruttori veri (revisione della PR #294): niente promesse di ciò che è spento
    for chiave, via in (("schermi_scritto", "si scrive"), ("immagini_enabled", "si allegano foto"),
                        ("allegati_enabled", " e file"), ("cassetto_enabled", "Cassetto"),
                        ("schermi_sezioni", "sul PC"), ("telefono_enabled", "il telefono"),
                        ("archivio_enabled", "«archiviala»")):
        c3 = Config()
        setattr(c3, chiave, False)
        t3 = c3._frase_sezioni(False)
        verifica(f"prompt con {chiave} spento: niente «{via.strip()}»", via not in t3 and t3.endswith(
            "lo dicono i dati del turno. "), t3)
    c3 = Config()
    c3.telefono_enabled = c3.schermi_sezioni = False
    verifica("senza telefono né PC a sezioni: nessun paragrafo", c3._frase_sezioni(True) == "")
    verifica("prompt stabile: due configurazioni uguali, lo stesso testo",
             Config()._frase_sezioni(True) == Config()._frase_sezioni(True))
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
    i = src.index("    def _tocco(self, t):")
    verifica("tocco: nessun dispositivo dell'ultimo turno a voce (tool_ctx.dispositivo azzerato)",
             "ctx.dispositivo = None" in src[i:i + 900])
    verifica("registro dei turni: il ciclo scrive il campo «dispositivo»",
             'self.rec["dispositivo"]' in src and "last_dispositivo" in src)


# ─────────────────────────── 2. #289: schermo_mostra con la pagina ───────────────────────────

def prova_pagina():
    print("── 2. #289: schermo_mostra con cosa=pagina ──")
    reg = build_registry(schermi=True)

    def call(args, hub, sc, livello=None, disp=None, ufficio=None, cfg=None):
        ctx = contesto(hub, sc, cfg=cfg, disp=disp, ufficio=ufficio)
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
    n0 = len(h.pagine)
    r, _ = call({"cosa": "pagina", "pagina": "ufficio"}, h, SC())
    verifica("Ufficio non installato: nemmeno chi amministra (come il prompt, che non lo nomina)",
             not r.get("ok") and len(h.pagine) == n0, r)
    r, _ = call({"cosa": "pagina", "pagina": "ufficio"}, h, SC(), ufficio=object())
    verifica("Ufficio installato: chi amministra sì", h.pagine[-1] == ("dario", "ufficio"), r)
    n = len(h.pagine)
    r, _ = call({"cosa": "pagina", "pagina": "ufficio"}, h, SC("Bianca", "familiare"), ufficio=object())
    verifica("Ufficio: un familiare no, e niente si sposta", not r.get("ok") and len(h.pagine) == n
             and "non c'è" in r["risposta_finale"], r)
    r, _ = call({"cosa": "pagina", "pagina": "ufficio"}, h, SC("Ada", "familiare"), ufficio=object())
    verifica("Ufficio: una bambina no", not r.get("ok") and len(h.pagine) == n, r)
    r, _ = call({"cosa": "pagina", "pagina": "documenti"}, h, SC("Ada", "familiare"))
    verifica("una bambina: Documenti sì (la pagina c'è anche per lei)", h.pagine[-1] == ("ada", "documenti"), r)
    n = len(h.pagine)
    r, _ = call({"cosa": "pagina", "pagina": "documenti"}, h, SC(None, "ospite", None))
    verifica("ospite: niente, solo per chi è riconosciuto dalla voce", not r.get("ok") and len(h.pagine) == n
             and "riconosco dalla voce" in r["risposta_finale"], r)
    r, _ = call({"cosa": "pagina", "pagina": "documenti"}, h, SC(come="conversazione", sessione=True))
    verifica("zona grigia da un dispositivo non suo: niente, e senza «chiamami per nome»",
             not r.get("ok") and len(h.pagine) == n and "per nome" not in r["risposta_finale"]
             and "non sono sicura" in r["risposta_finale"].lower(), r)
    # Zona grigia dal suo telefono (revisione della PR #294): la pagina si apre, sul suo schermo
    for come in ("breve", "conversazione"):
        r, ctx = call({"cosa": "pagina", "pagina": "documenti"}, h, SC(come=come, sessione=True),
                      disp=TEL_DARIO)
        verifica(f"zona grigia ({come}) dal telefono di Dario: Documenti sul suo schermo",
                 r.get("ok") and h.pagine[-1] == ("dario", "documenti")
                 and "schermo_pagina_proprio" in ctx.regole, r)
    n = len(h.pagine)
    r, _ = call({"cosa": "pagina", "pagina": "documenti"}, h,
                SC("Ada", "familiare", come="minore_piu_protetto", sessione=True), disp=TEL_DARIO)
    verifica("zona grigia col minore dal telefono di Dario: niente si sposta (né il suo, né quello di Ada)",
             not r.get("ok") and len(h.pagine) == n, r)
    for nome, sc in (("voce_proprietario, incerta fra Dario e Ada", VOCE_PROPRIETARIO()),
                     ("minore vicino a Dario", MINORE_VICINO())):
        for pagina in ("documenti", "ufficio"):
            r, _ = call({"cosa": "pagina", "pagina": pagina}, h, sc, disp=TEL_DARIO, ufficio=object())
            verifica(f"dal telefono di Dario, {nome}: {pagina} non si apre",
                     not r.get("ok") and len(h.pagine) == n and "non sono sicura" in r["risposta_finale"].lower(),
                     r)
    # L'Ufficio col livello vero del turno: dal suo telefono nella zona grigia (familiare) no;
    # con la voce riconosciuta e il livello di chi amministra sì
    r, _ = call({"cosa": "pagina", "pagina": "ufficio"}, h, SC("Dario", "familiare", come="breve",
                sessione=True), disp=TEL_DARIO, ufficio=object())
    UFF_VOCE = "L'Ufficio lo apro solo quando riconosco bene la tua voce: chiedimelo con una frase intera."
    verifica("Ufficio dal suo telefono nella zona grigia (livello familiare): non si apre, e la frase "
             "dice la voce, non «non c'è» (#299)",
             not r.get("ok") and len(h.pagine) == n and r["risposta_finale"] == UFF_VOCE, r)
    r, ctx = call({"cosa": "pagina", "pagina": "ufficio"}, h, SC("Dario", "familiare"), ufficio=object())
    verifica("Ufficio a chi amministra con la voce certa ma il livello familiare del turno: non si apre, "
             "la frase della voce e la regola schermo_ufficio_voce (#299)",
             not r.get("ok") and len(h.pagine) == n and r["risposta_finale"] == UFF_VOCE
             and "schermo_ufficio_voce" in ctx.regole, r)
    # Contrari (#299): «non c'è» resta per chi davvero non ce l'ha
    for nome, sc, uff in (("un familiare", SC("Bianca", "familiare"), object()),
                          ("una bambina", SC("Ada", "familiare"), object()),
                          ("chi amministra senza l'ufficio installato", SC("Dario", "familiare"), None)):
        r, _ = call({"cosa": "pagina", "pagina": "ufficio"}, h, sc, ufficio=uff)
        verifica(f"Ufficio a {nome}: «Sul tuo schermo la pagina Ufficio non c'è.», mai la frase della voce",
                 r["risposta_finale"] == "Sul tuo schermo la pagina Ufficio non c'è.", r)
    r, _ = call({"cosa": "pagina", "pagina": "ufficio"}, h, SC("Dario", "amministra"), disp=TEL_DARIO,
                ufficio=object())
    verifica("Ufficio dal suo telefono con la voce certa e il livello amministra: si apre",
             r.get("ok") and h.pagine[-1] == ("dario", "ufficio"), r)
    n = len(h.pagine)
    r, ctx = call({"cosa": "pagina", "pagina": "documenti"}, Hub(abbinati=[(1, "dario")]),
                  SC(come="breve", sessione=True), disp=TEL_DARIO)
    verifica("zona grigia dal suo telefono, schermo chiuso: «Lo trovi in Le mie cose…», non «non ne hai uno»",
             r["risposta_finale"].startswith("Lo trovi in Le mie cose"), r)
    cfg_spento = Config()
    cfg_spento.cassetto_enabled = False
    r, _ = call({"cosa": "pagina", "pagina": "cassetto"}, h, SC(), cfg=cfg_spento)
    verifica("Cassetto spento: la pagina non c'è", not r.get("ok") and len(h.pagine) == n, r)
    r, _ = call({"cosa": "agendina", "pagina": "liste"}, h, SC())
    verifica("cosa fuori elenco con la pagina scritta: errore, niente si apre",
             not r.get("ok") and len(h.pagine) == n and "cosa=pagina" in r["risposta_finale"], r)
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

    class SrvSenzaFile:
        def __init__(self, c):
            self.c = c

        def per_pc(self):
            return self.c

    # La consegna dei documenti: assente e telefono senza file
    d = RemoteDelivery(SrvSenzaFile(None), LocalDelivery(TMP / "riserva"), "portatile").deliver("A", "pdf", b"%PDF")
    verifica("consegna, portatile non collegato: «tra i miei documenti, perché il portatile non è collegato»",
             d["dove"] == "tra i miei documenti, perché il portatile non è collegato", d["dove"])
    tel = types.SimpleNamespace(esecutore=None, canale="telefono")
    d = RemoteDelivery(SrvSenzaFile(tel), LocalDelivery(TMP / "riserva"), "portatile").deliver("B", "pdf", b"%PDF")
    verifica("consegna dal telefono: il motivo sul PC, vero da qualunque dispositivo (niente «da cui mi parli»)",
             d["dove"] == "tra i miei documenti, perché il portatile non è collegato", d["dove"])
    d = RemoteDelivery(SrvSenzaFile(types.SimpleNamespace(esecutore={"file": False})),
                       LocalDelivery(TMP / "riserva"), "portatile").deliver("C", "pdf", b"%PDF")
    verifica("consegna a un PC che non riceve file: «il portatile non riceve file»",
             d["dove"] == "tra i miei documenti, perché il portatile non riceve file", d["dove"])

    # Il documento nella zona grigia (revisione della PR #294): dal suo telefono la pagina Documenti
    from calliope.tools.documenti import _su_pagina
    chiuso = Hub(abbinati=[(1, "dario")])
    verifica("documento, zona grigia dal suo telefono: «in Le mie cose, alla voce Documenti»",
             _su_pagina(contesto(chiuso, SC(come="breve", sessione=True), disp=TEL_DARIO)))
    verifica("documento, zona grigia da un telefono non suo: la frase di sempre",
             not _su_pagina(contesto(chiuso, SC(come="breve", sessione=True),
                                     disp=dispositivo.descrivi("telefono"))))

    # I lavori dell'agente: la scelta dei documenti, decisa alla consegna da `lav.persona`
    # (revisione della PR #294), anche per un lavoro ripreso da disco dopo un riavvio
    import threading
    from calliope.agenti import ripresa
    import calliope.agenti.risultato as AR
    dest = TMP / "lavoro"
    dest.mkdir(exist_ok=True)
    (dest / "risultato.md").write_text("# Le api", encoding="utf-8")

    def servizio(hub, server):
        svc = Lavori.__new__(Lavori)
        svc.consegna = types.SimpleNamespace(nome="portatile", server=server)
        svc.log, svc.schermi, svc.lavori, svc._lock = (lambda m: None), hub, [], threading.Lock()
        return svc

    def ripreso():
        lav0 = Lavoro("l1", "ricerca", "le api", persona="dario", persona_nome="Dario", titolo="Le api")
        return ripresa.ricostruisci(ripresa.voce(lav0, time.time()), Lavoro)
    PAG = "in Le mie cose, alla voce Lavori e programmi"
    for nome, hub, server, attesa in (
            ("aperto, dal telefono", Hub(abbinati=[(1, "dario")], aperti=[1]), SrvSenzaFile(tel), PAG),
            ("chiuso", Hub(abbinati=[(1, "dario")]), SrvSenzaFile(None), PAG),
            ("assente, dal telefono", Hub(), SrvSenzaFile(tel),
             "tra i miei file, nella cartella Lavori, perché il portatile non è collegato"),
            ("assente, PC senza file", Hub(), SrvSenzaFile(types.SimpleNamespace(esecutore={"file": False})),
             "tra i miei file, nella cartella Lavori, perché il portatile non riceve file")):
        lav = ripreso()
        ris = {"file": ["risultato.md"]}
        Lavori._consegna_risultato(servizio(hub, server), lav, ris, dest)
        verifica(f"lavoro ripreso dopo un riavvio, schermo {nome}: «{attesa}»", ris.get("dove") == attesa
                 and "server" not in ris["dove"] and "satellite" not in ris["dove"]
                 and "da cui mi parli" not in ris["dove"], ris.get("dove"))
    lav = Lavoro("l3", "ricerca", "x", persona=None)
    svc = servizio(Hub(abbinati=[(1, "dario")]), SrvSenzaFile(None))
    ris = {}
    svc._dove_in_casa(lav, ris, "x")
    verifica("lavoro senza persona: la cartella (niente pagina)", ris["dove"].startswith("tra i miei file"))
    rotto = Lavoro("l2", "ricerca", "x", persona="dario")
    rotto.ha_pagina = lambda: 1 / 0
    ris = {}
    svc._dove_in_casa(rotto, ris, "x")
    verifica("contrario: ha_pagina guasta → la cartella", ris["dove"].startswith("tra i miei file"))
    # Lavori e programmi mostra gli ultimi LAVORI_FINITI_PAGINA: fuori da lì, la cartella
    lav = ripreso()
    lav.stato = "fatto"
    ris = {}
    svc._dove_in_casa(lav, ris, "il portatile non è collegato")
    prima = AR.recenti
    try:
        AR.recenti = lambda svc_, persona, nome=None, n=3: [lav]
        verifica("frase: il lavoro fra gli ultimi della pagina → «in Le mie cose…»",
                 svc.dove_detto(lav, ris) == PAG, svc.dove_detto(lav, ris))
        svc.schermi = Hub()
        verifica("frase: lo schermo revocato dopo la consegna → la cartella",
                 svc.dove_detto(lav, ris).startswith("tra i miei file"), svc.dove_detto(lav, ris))
        svc.schermi = Hub(abbinati=[(1, "dario")])
        AR.recenti = lambda svc_, persona, nome=None, n=3: []
        verifica("frase: il lavoro non più fra gli ultimi sei → la cartella, non «Lo trovi in Le mie cose»",
                 svc.dove_detto(lav, ris).startswith("tra i miei file"), svc.dove_detto(lav, ris))
    finally:
        AR.recenti = prima
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
    cost = re.search(r'const PAGINA_VERSIONE = "(calliope-telefono-pagina-v\d+)";', js)
    cache = re.search(r'const CACHE = "(calliope-telefono-pagina-v\d+)";', sw)
    verifica("il telefono manda nel primo «ciao» la versione della pagina che gira, uguale alla cache di sw.js",
             cost and cache and cost.group(1) == cache.group(1) and "pagina: PAGINA_VERSIONE" in js
             and "caches.keys" not in js, (cost and cost.group(1), cache and cache.group(1)))


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
