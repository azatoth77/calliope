import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della Conversazione con le schede dentro, i filtri e la ricerca (28/10/2026,
issue #242, passo 3 di docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md).

- la scheda del turno (`schede.per_conversazione`): una copia `storica` per i tipi di contenuto
  (senza le chiavi «_», «Scarica» e scadenza), un rimando per i tipi vivi o pesanti e per una copia
  oltre il tetto, niente per la risposta scritta, la chat, il cruscotto, la voce nuova, archivio e
  ufficio;
- `Brain._invia_schede` lega la scheda al messaggio della persona solo con l'identità certa; la
  stessa scheda di nuovo nello stesso turno sostituisce quella di prima; al più quattro;
  `Brain.record_tocco` lega la lista aggiornata al turno del tocco;
- `conversazione.turni`: le schede nel meta, passate da `oscura` (non le chiavi), tolte in un turno
  riservato; un turno `non_conservare` non va su disco, con le sue schede;
- `voce_chat`: i canali voce, scritto, tocco e modulo (uno sconosciuto vale «voce»), il luogo della
  conversazione non vale per il tocco e il modulo; il Markdown con il canale e le schede;
- il modulo inviato entra nella storia con il canale «modulo» e lo schermo;
- `ArchivioConversazioni.chat_filtra` e `Schermi.chat_filtrata`: oggi, ieri, solo schede, ricerca per
  parole con testo ostile (virgolette, operatori di FTS5, `--`, `<script>`, solo simboli), mai i
  turni di un'altra persona né degli ospiti;
- `POST /api/conversazione` sul server vero: lo schermo personale vede solo i turni del suo
  proprietario (il tutore non vede quelli del ragazzo, il ragazzo non vede quelli del tutore), lo
  schermo di stanza 403, senza sessione 401, dati non validi 400, le ricerche oltre 20 al minuto 429
  con Retry-After;
- dalla revisione della PR #271: una risposta riservata non arriva nell'archivio da una scheda
  (il caso del contratto, e `schermo_mostra` con risposta, testo e ultima), la stima dei token
  non conta le copie, le copie leggere oltre gli ultimi turni e il dettaglio al tocco (solo dai
  propri turni), foto e file mai legati, il calcolo senza oscura, il timer senza «chi»; dalla
  seconda, il modulo di un tool riservato (modello_compila, anagrafica_salva) che non lega le schede
  e fa il turno riservato.

Tutto in una cartella temporanea. ~3 s.
"""

import datetime
import json
import shutil
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import httpx

from calliope.config import Config
from calliope.schermi import ArchivioSchermi, Mittente, Schermi, schede

TMP = Path(tempfile.mkdtemp(prefix="calliope-conv-schede-"))
ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({str(dettaglio)[:300]})" if dettaglio else ""),
          flush=True)
    if not ok:
        ERRORI.append(nome)


DARIO = Mittente("dario", "Dario", "amministra", True)
GRIGIA = Mittente("dario", "Dario", "familiare", False)


# ─────────────────────────── 1. la scheda del turno ───────────────────────────
def prova_per_conversazione():
    pc = schede.per_conversazione
    lista = schede.lista("spesa", ["latte", "pane"], aggiunti=["pane"])
    c = pc(lista)
    verifica("lista: copia storica con la chiave, le voci e la sezione",
             c and c.get("storica") is True and c["chiave"] == "lista:spesa"
             and [v["testo"] for v in c["voci"]] == ["latte", "pane"] and c["sezione"] == "cose/liste"
             and "scade" not in c and not c.get("rimando"), c)
    doc = schede.documento_markdown("Relazione", "# R\n\nok", chiave="lavoro:L9")
    doc["_scarica"] = {"markdown": "segreto"}
    c = pc(doc)
    verifica("documento: copia senza le chiavi «_» né «Scarica»",
             c and c.get("storica") and not any(str(k).startswith("_") for k in c)
             and "scarica" not in c and c.get("markdown") == "# R\n\nok", c)
    grosso = {**schede.testo("Lungo", "x", schede.PERSONALE), "testo": "parola " * 4000}
    c = pc(grosso)
    verifica("oltre il tetto di byte: un rimando con tipo, titolo e sezione",
             c and c.get("rimando") is True and c["tipo"] == "testo" and "testo" not in c
             and c["titolo"] == "Lungo", c)
    lav = schede.lavoro("Riepilogo bollette", "testo", "in_corso", "sto leggendo", ident="L3")
    c = pc(lav)
    verifica("lavoro: sempre un rimando (è vivo), con la chiave per ritrovarlo",
             c and c.get("rimando") and c.get("chiave") == lav.get("chiave")
             and c["sezione"] == "cose/lavori", c)
    nessuna = [pc(schede.risposta("d", "r", schede.PERSONALE)), pc({"tipo": "chat"}),
               pc({"tipo": "cruscotto"}), pc({"tipo": "conoscente", "titolo": "Voce nuova"}),
               pc({"tipo": "archivio"}), pc({"tipo": "ufficio"}), pc({"tipo": "vuota"}), pc("x")]
    verifica("niente per risposta scritta, chat, cruscotto, voce nuova, archivio, ufficio, vuota",
             nessuna == [None] * 8, nessuna)


# ─────────────────────────── 2. Brain lega la scheda al turno ───────────────────────────
def brain_finto(storia):
    from calliope.brain import Brain
    b = SimpleNamespace(history=storia, last_schede_mandate=[], _rule=lambda n: None)
    b.lega_scheda_al_turno = lambda c, m=None: Brain.lega_scheda_al_turno(b, c, m)
    b.ATTESA_SCHEDE_S = Brain.ATTESA_SCHEDE_S
    b._in_attesa = lambda c, p: Brain._in_attesa(b, c, p)
    b._lega_in_attesa = lambda m: Brain._lega_in_attesa(b, m)
    return b


class HubFinto:
    def __init__(self):
        self.inviate = []

    def invia(self, card, sender):
        self.inviate.append(card)
        return {"schermi": ["telefono"], "motivo": None}


def prova_brain():
    from calliope.brain import Brain
    storia = [{"role": "user", "content": "di prima"}, {"role": "assistant", "content": "ok"},
              {"role": "user", "content": "aggiungi il pane"}]
    b = brain_finto(storia)
    hub = HubFinto()
    Brain._invia_schede(b, hub, [schede.lista("spesa", ["latte"])], DARIO)
    Brain._invia_schede(b, hub, schede.lista("spesa", ["latte", "pane"]), DARIO)
    verifica("la scheda va sul messaggio della persona di questo turno, la stessa chiave sostituisce",
             "_schede" not in storia[0] and len(storia[2].get("_schede", [])) == 1
             and [v["testo"] for v in storia[2]["_schede"][0]["voci"]] == ["latte", "pane"],
             storia[2].get("_schede"))
    Brain._invia_schede(b, hub, [schede.calcolo(f"{i}+1", str(i + 1)) for i in range(6)], DARIO)
    verifica("al più quattro schede per turno (le ultime)",
             len(storia[2]["_schede"]) == 4 and storia[2]["_schede"][-1]["risultato"] == "6")
    s2 = [{"role": "user", "content": "zona grigia"}]
    b2 = brain_finto(s2)
    Brain._invia_schede(b2, hub, [schede.calcolo("1+1", "2")], GRIGIA)
    Brain._invia_schede(b2, hub, [schede.calcolo("1+1", "2")], Mittente())
    verifica("senza l'identità certa (zona grigia, ospite) la scheda non resta col turno",
             "_schede" not in s2[0] and len(hub.inviate) == 10, s2)
    # Il tocco: la lista aggiornata dal risultato del tool
    s3 = []
    b3 = brain_finto(s3)
    b3._check_conversation = lambda: None
    b3.dalla_proiezione = lambda: None
    b3.salva_conversazione = lambda: None
    ris = json.dumps({"ok": True, "conferma": "Tolto.", "scheda": schede.lista("spesa", ["pane"])})
    Brain.record_tocco(b3, "(Ho tolto «latte» dalla lista della spesa toccando lo schermo.)",
                       "lista_togli", {"lista": "spesa", "voce": "latte"}, ris, "Tolto.")
    verifica("il tocco: la lista aggiornata resta col suo turno",
             s3 and s3[0]["role"] == "user" and s3[0].get("_schede", [{}])[0].get("chiave")
             == "lista:spesa", s3[:1])


# ─────────────────────────── 3. turni, voce_chat, Markdown, modulo ───────────────────────────
def prova_turni():
    from calliope.conversazione import RISERVATA, turni
    from calliope.conversazioni import chat_markdown, voce_chat
    t0 = time.time() - 30
    timer = schede.per_conversazione(schede.timer({"id": 7, "label": "pasta", "due": t0 + 480,
                                                   "created": t0, "owner_name": "Dario"}))
    testo = schede.per_conversazione(schede.testo("Mail", "scrivi a a@b.it", schede.PERSONALE))
    msg = [{"role": "user", "content": "metti un timer", "_turno": {"t": t0, "canale": "voce",
                                                                     "luogo": "Cucina"},
            "_schede": [timer, testo]},
           {"role": "assistant", "content": "Fatto."},
           {"role": "user", "content": "Cosa dice il contratto?", "_turno": {"t": t0 + 5},
            "_schede": [schede.per_conversazione(schede.testo("Contratto", "canone 900",
                                                              schede.PERSONALE))]},
           {"role": "tool", "name": "archivio_cerca", "content": "{}"},
           {"role": "assistant", "content": "Il canone è di 900 euro."}]
    tt = turni(msg, frozenset({"archivio_cerca"}))
    s0 = tt[0]["meta"]["schede"]
    verifica("le schede del turno nel meta, con il canale e il luogo",
             tt[0]["meta"]["canale"] == "voce" and [x["tipo"] for x in s0] == ["timer", "testo"], tt[0])
    verifica("i testi delle schede passano da oscura, le chiavi no (l'istante del timer resta)",
             "a@b.it" not in json.dumps(s0) and s0[0]["chiave"] == timer["chiave"]
             and s0[0]["timer"][0]["fine"] == t0 + 480, s0)
    verifica("turno riservato: niente schede, come la risposta",
             tt[1]["risposta"] == RISERVATA and "schede" not in (tt[1].get("meta") or {}), tt[1])
    # voce_chat: i canali
    v = [voce_chat(i, t0, "d", "r", {"canale": c}, "Studio") for i, c in
         enumerate(["voce", "scritto", "tocco", "modulo", "<script>"])]
    verifica("canali: voce, scritto, tocco, modulo; uno sconosciuto vale «voce»",
             [x["canale"] for x in v] == ["voce", "scritto", "tocco", "modulo", "voce"], v)
    verifica("il luogo della conversazione vale per voce e scritto, non per tocco e modulo",
             [x["luogo"] for x in v[:4]] == ["Studio", "Studio", "", ""]
             and voce_chat(9, t0, "d", "r", {"canale": "modulo", "luogo": "Telefono"}, "Studio")["luogo"]
             == "Telefono")
    con = voce_chat(10, t0, "d", "r", tt[0]["meta"], "Cucina")
    verifica("voce_chat porta le schede del turno", [x["tipo"] for x in con["schede"]] == ["timer", "testo"])
    md = chat_markdown([con, v[2]])
    verifica("Markdown: il canale e le schede del turno (tipo e titolo)",
             "Cucina · a voce" in md and "con un tocco" in md and "*Scheda: Timer · Timer pasta*" in md, md)
    # non_conservare: niente su disco, nemmeno le schede
    from calliope.conversazioni import ArchivioConversazioni
    from calliope.conversazione import Conversazione
    arch = ArchivioConversazioni(TMP / "nc.db", giorni=30, avvia=False, log=lambda m: None)
    c = Conversazione("persona:dario")
    tz = turni([{"role": "user", "content": "zona grigia", "_turno": {"t": t0, "conserva": False},
                 "_schede": [timer]}, {"role": "assistant", "content": "ok"}])
    arch.archivia(c, tz, "dario", "Dario", ospite=False)
    verifica("un turno da non conservare non va su disco, con le sue schede", arch.chat("dario") == [])
    arch.close()


def prova_modulo():
    from calliope.schermi import moduli
    chiusi = []
    hub = SimpleNamespace(moduli=SimpleNamespace(chiudi=lambda m, nota, stato=None: chiusi.append(stato)),
                          invia=lambda c, mitt: {})
    doc = schede.documento({"blocchi": [{"tipo": "paragrafo", "testo": "x"}]}, "docx", "fattura.docx")
    m = SimpleNamespace(stato="aperto", chiave="m1", livello="amministra", titolo="Fattura",
                        campi=[{"nome": "piva", "etichetta": "Partita IVA"}], mittente=DARIO,
                        riprendi=lambda valori, turno: {"ok": True, "frase": "Pronta.", "scheda": doc})
    storia = []
    brain = brain_finto(storia)
    brain.pending = None
    brain.eventi_attivo = lambda: False
    brain.record_announcement = lambda *a, **k: storia.append({"role": "assistant", "content": a[0]})
    item = {"_modulo": m, "valori": {"piva": "12345678901"}, "schermo": "Telefono di Dario",
            "arrivato": time.time()}
    out = moduli.completa(hub, item, brain, 3)
    u = storia[0] if storia else {}
    verifica("modulo: nella storia col canale «modulo» e lo schermo, mai i valori",
             u.get("_turno", {}).get("canale") == "modulo"
             and u["_turno"].get("luogo") == "Telefono di Dario" and "12345678901" not in u["content"]
             and out["frase"] == "Pronta.", u)
    verifica("modulo: la scheda del risultato resta col turno",
             [x["tipo"] for x in u.get("_schede", [])] == ["documento"], u.get("_schede"))


def prova_modulo_riservato():
    """Seconda revisione della PR #271: un tool riservato completato col modulo (la fattura di
    modello_compila, la rubrica di anagrafica_salva) non lega le sue schede, e il turno del modulo è
    riservato nell'archivio."""
    from calliope.conversazione import RISERVATA, turni
    from calliope.schermi import moduli
    riservati = {"modello_compila", "anagrafica_salva"}
    for tool, titolo, frase in (("modello_compila", "Fattura per Rossi", "Ho preparato la fattura per Rossi: totale 1.220 euro."),
                                ("anagrafica_salva", "Cliente Rossi", "Ho salvato Mario Rossi, via Verdi 3, Milano.")):
        inviate = []
        hub = SimpleNamespace(moduli=SimpleNamespace(chiudi=lambda m, nota, stato=None: None),
                              invia=lambda c, mitt: inviate.append(c) or {})
        doc = schede.documento({"blocchi": [{"tipo": "paragrafo", "testo": "Rossi Mario · 2 ore di consulenza · totale 1.220 euro"}]},
                               "pdf", "fattura-rossi.pdf")
        m = SimpleNamespace(stato="aperto", chiave="m2", livello="amministra", titolo=titolo, tool=tool,
                            campi=[{"nome": "piva", "etichetta": "Partita IVA"}], mittente=DARIO,
                            riprendi=lambda valori, turno, d=doc, f=frase: {"ok": True, "frase": f, "scheda": d})
        storia = [{"role": "user", "content": f"Prepara {titolo.lower()}", "_turno": {"t": 1.0}},
                  {"role": "assistant", "content": "Mi servono dei dati: li puoi scrivere sullo schermo."}]
        brain = brain_finto(storia)
        brain.pending = None
        brain.eventi_attivo = lambda: False
        brain.tools = SimpleNamespace(get=lambda n: SimpleNamespace(name=n, riservato=n in riservati))
        brain.record_announcement = lambda *a, **k: storia.append({"role": "assistant", "content": a[0]})
        moduli.completa(hub, {"_modulo": m, "valori": {"piva": "12345678901"}, "schermo": "Telefono di Dario",
                              "arrivato": time.time()}, brain, 4)
        u = storia[2] if len(storia) > 2 else {}
        verifica(f"modulo di {tool} (riservato): la scheda col segno prima di partire, non legata al turno",
                 inviate and inviate[0].get("_riservata") is True and "_schede" not in u
                 and schede.per_conversazione(inviate[0]) is None, u)
        tt = turni(storia)
        testo = json.dumps(tt, ensure_ascii=False)
        verifica(f"modulo di {tool}: il turno del modulo riservato nell'archivio, la frase non in chiaro",
                 tt[-1]["riservato"] and tt[-1]["risposta"] == RISERVATA and "1.220" not in testo
                 and "Verdi" not in testo and "schede" not in (tt[-1].get("meta") or {}), tt[-1])


# ─────────────────────────── 4. filtri e ricerca ───────────────────────────
def cfg_prova() -> Config:
    c = Config()
    c.memory_db = str(TMP / "memoria.db")
    c.config_dir = str(TMP)
    c.conversazioni_db = str(TMP / "conversazioni.db")
    return c


def archivio_pieno():
    from calliope.conversazione import Conversazione, turni
    from calliope.conversazioni import ArchivioConversazioni
    arch = ArchivioConversazioni(TMP / "conv.db", giorni=60, avvia=False, log=lambda m: None)
    oggi = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    ieri = oggi - 86400 + 3600 * 10
    altro = oggi - 86400 * 5
    lista = schede.per_conversazione(schede.lista("spesa", ["latte"]))

    def t(domanda, risposta, quando, canale="voce", sch=None):
        return [{"role": "user", "content": domanda, "_turno": {"t": quando, "canale": canale,
                                                                "luogo": "Cucina"},
                 **({"_schede": sch} if sch else {})}, {"role": "assistant", "content": risposta}]
    c = Conversazione("persona:dario")
    msg = (t("Quando è nato Manzoni?", "Il 7 marzo 1785.", altro)
           + t("Aggiungi latte alla spesa", "Fatto, l'ho aggiunto.", ieri, sch=[lista])
           + t("Che ore sono?", "Le dieci.", ieri + 60)
           + t("Ricordami la bolletta", "Te lo ricordo domani.", min(time.time() - 5, oggi + 60), "scritto"))
    arch.archivia(c, turni(msg), "dario", "Dario", ospite=False)
    b = Conversazione("persona:bianca")
    arch.archivia(b, turni(t("Il segreto di Bianca", "Lo tengo per te.", ieri)), "bianca", "Bianca",
                  ospite=False)
    teo = Conversazione("persona:teo")
    arch.archivia(teo, turni(t("Compiti di Teo sulla bolletta", "Va bene.", ieri)), "teo", "Teo",
                  ospite=False)
    g = Conversazione("ospite:locale")
    arch.archivia(g, turni(t("ospite che chiede la bolletta", "ciao", ieri)), None, None, ospite=True)
    return arch


def prova_filtri(arch):
    hub = Schermi(cfg_prova(), ArchivioSchermi(str(TMP / "filtri.db")), log=lambda m: None)
    hub.chat_fonte = arch
    tel = {"id": 1, "proprietario": "dario"}
    dom = lambda r: [x["domanda"] for x in r.get("turni", [])]
    tutto = arch.chat_filtra("dario")
    verifica("senza filtri: i turni di Dario e di nessun altro, dal più vecchio",
             dom(tutto)[0] == "Quando è nato Manzoni?" and len(tutto["turni"]) == 4
             and not any("Bianca" in d or "Teo" in d or "ospite" in d for d in dom(tutto)), dom(tutto))
    r = hub.chat_filtrata(tel, "oggi")
    verifica("Oggi: solo i turni di oggi", dom(r) == ["Ricordami la bolletta"], r)
    r = hub.chat_filtrata(tel, "ieri")
    verifica("Ieri: i turni di ieri, in ordine",
             dom(r) == ["Aggiungi latte alla spesa", "Che ore sono?"], r)
    r = hub.chat_filtrata(tel, None, True)
    verifica("Solo schede: i turni con una scheda, con la scheda",
             dom(r) == ["Aggiungi latte alla spesa"] and r["turni"][0]["schede"][0]["tipo"] == "lista", r)
    r = hub.chat_filtrata(tel, "oggi", True)
    verifica("Oggi e Solo schede insieme: niente, con la nota", r["turni"] == [] and r["nota"], r)
    r = hub.chat_filtrata(tel, None, False, "bolletta")
    verifica("ricerca: le parole nei turni di Dario, mai in quelli di Teo, di Bianca o degli ospiti",
             dom(r) == ["Ricordami la bolletta"], r)
    r = hub.chat_filtrata(tel, None, False, "manzon")
    verifica("ricerca per prefisso", dom(r) == ["Quando è nato Manzoni?"], r)
    ostili = ['" OR 1=1 --', "NEAR(latte bolletta)", "bolletta*", "<script>alert(1)</script>",
              "'; DROP TABLE turni; --", "latte\" OR \"x", "***", "AND OR NOT", "\x00\x01"]
    esiti = {o: hub.chat_filtrata(tel, None, False, o) for o in ostili}
    verifica("ricerca con testo ostile: nessun errore, mai i turni di altri",
             all("_stato" not in r and not any("Teo" in d or "Bianca" in d for d in dom(r))
                 for r in esiti.values()), {k: (dom(v), v.get("nota")) for k, v in esiti.items()})
    verifica("…e l'archivio è intatto", len(arch.chat("dario")) == 4)
    verifica("solo simboli: nessuna parola da cercare, lo dice",
             esiti["***"]["turni"] == [] and "parola" in esiti["***"]["nota"], esiti["***"])
    r = hub.chat_filtrata({"id": 2, "proprietario": "teo"}, None, False, "bolletta")
    verifica("il ragazzo cerca solo nei suoi turni", dom(r) == ["Compiti di Teo sulla bolletta"], r)
    r = hub.chat_filtrata({"id": 3}, "ieri")
    verifica("uno schermo di stanza non ha la conversazione", r.get("_stato") == 403, r)
    hub.archivio.close()


# ─────────────────────────── 5. il server vero ───────────────────────────
def prova_server(arch):
    from calliope.schermi.server import ServerSchermi
    hub = Schermi(cfg_prova(), ArchivioSchermi(str(TMP / "server.db")), log=lambda m: None)
    hub.chat_fonte = arch
    srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
    hub.server = srv
    c = httpx.Client(base_url=f"http://127.0.0.1:{srv.port}", timeout=5)
    _, tok_d = hub.archivio.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario")
    _, tok_t = hub.archivio.crea_con_token("cameretta", proprietario="teo", proprietario_nome="Teo")
    _, tok_s = hub.archivio.crea_con_token("cucina")
    hub._rinfresca()

    def accedi(t):
        return c.post("/api/accedi", headers={"Authorization": f"Bearer {t}"}).json()["sessione"]
    h_d = {"X-Calliope-Sessione": accedi(tok_d)}
    h_t = {"X-Calliope-Sessione": accedi(tok_t)}
    h_s = {"X-Calliope-Sessione": accedi(tok_s)}
    dom = lambda r: [x["domanda"] for x in r.json().get("turni", [])]
    r = c.post("/api/conversazione", headers=h_d, json={"giorno": "ieri"})
    verifica("/api/conversazione: Ieri dallo schermo di Dario, solo i suoi turni",
             r.status_code == 200 and dom(r) == ["Aggiungi latte alla spesa", "Che ore sono?"]
             and r.headers.get("cache-control") == "no-store", r.text[:300])
    r = c.post("/api/conversazione", headers=h_d, json={"schede": True})
    verifica("…Solo schede con la scheda dentro",
             r.status_code == 200 and r.json()["turni"][0]["schede"][0]["chiave"] == "lista:spesa", r.text[:300])
    r = c.post("/api/conversazione", headers=h_t, json={"giorno": "ieri"})
    verifica("lo schermo del ragazzo: solo i turni del ragazzo", dom(r) == ["Compiti di Teo sulla bolletta"], r.text[:300])
    r = c.post("/api/conversazione", headers=h_d, json={"testo": "Teo"})
    verifica("il tutore non trova i turni del ragazzo", r.status_code == 200 and dom(r) == [], r.text[:300])
    r = c.post("/api/conversazione", headers=h_s, json={"giorno": "oggi"})
    verifica("schermo di stanza: 403", r.status_code == 403, r.status_code)
    r = c.post("/api/conversazione", headers={"X-Calliope-Sessione": "falsa"}, json={})
    verifica("senza sessione: 401", r.status_code == 401, r.status_code)
    cattivi = [{"giorno": "domani"}, {"schede": "sì"}, {"testo": 3}, ["x"]]
    stati = [c.post("/api/conversazione", headers=h_d, json=x).status_code for x in cattivi]
    verifica("dati non validi: 400", stati == [400] * 4, stati)
    r = c.post("/api/conversazione", headers={**h_d, "Content-Type": "application/json"},
               content=json.dumps({"testo": "a" * 5000}).encode())
    verifica("corpo troppo grande: rifiutato", r.status_code in (400, 413), r.status_code)
    # Una ricerca c'è già stata («Teo»): ne restano 19 nel minuto
    stati = [c.post("/api/conversazione", headers=h_d, json={"testo": f"bolletta {i}"}).status_code
             for i in range(20)]
    r = c.post("/api/conversazione", headers=h_d, json={"testo": "bolletta"})
    verifica("le ricerche oltre 20 al minuto: 429 con Retry-After",
             stati.count(200) == 19 and stati[-1] == 429 and r.status_code == 429 and int(r.headers.get("retry-after", 0)) > 0
             and r.json().get("riprova_s"), (stati, r.status_code, r.headers.get("retry-after")))
    r = c.post("/api/conversazione", headers=h_d, json={"giorno": "oggi"})
    verifica("…le letture senza ricerca hanno il loro conto", r.status_code == 200, r.status_code)
    srv.ferma()
    hub.archivio.close()
    c.close()


# ─────────────────────────── 6. dalla revisione della PR #271 ───────────────────────────
class HubUltima(HubFinto):
    """Come HubFinto, e ricorda l'ultima scheda (lo stesso oggetto, come hub.ricorda)."""

    def __init__(self):
        super().__init__()
        self._ultima = None

    def invia(self, card, sender):
        self._ultima = card
        return super().invia(card, sender)

    def ultima(self, sender):
        return self._ultima


def prova_riservato():
    """Bloccante 1: una risposta riservata non arriva nell'archivio passando da una scheda."""
    from calliope.brain import Brain
    from calliope.conversazione import turni
    from calliope.tools import schermi as TS
    hub = HubUltima()
    # Turno 1: «cosa dice il contratto?» → archivio_cerca (riservato): la scheda di quel turno ha il
    # segno e non si lega
    storia = [{"role": "user", "content": "Cosa dice il contratto d'affitto?", "_turno": {"t": 1.0}}]
    b = brain_finto(storia)
    b.last_private = True
    doc = schede.documento({"blocchi": [{"tipo": "paragrafo", "testo": "Canone 850 euro, scade il 31/12."}]},
                           "pdf", "contratto.pdf")
    Brain._invia_schede(b, hub, [doc], DARIO)
    verifica("una scheda mandata in una risposta con un tool riservato non resta col turno",
             doc.get("_riservata") is True and "_schede" not in storia[0], storia[0])
    storia += [{"role": "tool", "name": "archivio_cerca", "content": "{}"},
               {"role": "assistant", "content": "Il contratto scade il 31/12, canone 850 euro, IBAN IT60X0542811101000000123456."}]
    # Turno 2: «scrivimelo sullo schermo» con ogni `cosa` che ripete la risposta di prima
    ctx = SimpleNamespace(speaker_ctx=SimpleNamespace(current_speaker=None, current_level="familiare"),
                          speakers=None, risposta_precedente={"testo": storia[-1]["content"],
                                                              "tool": ["archivio_cerca"], "riservata": True})
    casi = {}
    for cosa, testo in (("risposta", ""), ("testo", "Canone 850 euro, scade il 31/12."), ("ultima", "")):
        card, err = TS._scheda_per(ctx, cosa, "", hub, DARIO, testo)
        casi[cosa] = (card or {}).get("_riservata") is True and schede.per_conversazione(card) is None
    verifica("«scrivimelo sullo schermo» dopo una risposta riservata: risposta, testo e ultima col segno, mai copiate",
             all(casi.values()), casi)
    # Il turno 2 dentro Brain e poi nell'archivio: niente canone
    storia.append({"role": "user", "content": "Scrivimelo sullo schermo", "_turno": {"t": 2.0}})
    b.last_private = False
    card, _ = TS._scheda_per(ctx, "risposta", "", hub, DARIO)
    Brain._invia_schede(b, hub, [card], DARIO)
    storia.append({"role": "assistant", "content": "Fatto, è sullo schermo."})
    tt = turni(storia, frozenset({"archivio_cerca"}))
    verifica("il caso del contratto: nell'archivio né canone né IBAN, in nessun turno",
             "850" not in json.dumps(tt, ensure_ascii=False) and not any((t.get("meta") or {}).get("schede") for t in tt), tt)
    # Le altre risposte riservate (stanza_cerca, conversazione_cerca) passano da last_private come
    # archivio_cerca; una risposta di prima non riservata sì
    ctx.risposta_precedente = {"testo": "Domani sole.", "tool": ["meteo_leggi"], "riservata": False}
    card, _ = TS._scheda_per(ctx, "risposta", "", hub, DARIO)
    verifica("…e una risposta non riservata si copia", schede.per_conversazione(card) is not None)
    import re
    rr = {}
    for nome, file in (("stanza_cerca", "stanza.py"), ("conversazione_cerca", "conversazioni.py")):
        src = (Path(__file__).resolve().parent.parent / "calliope" / "tools" / file).read_text(encoding="utf-8")
        i = src.find(f'name="{nome}"') if f'name="{nome}"' in src else src.find(f'"{nome}"')
        rr[nome] = i >= 0 and bool(re.search(r"riservato=True", src[i:i + 3000]))
    verifica("stanza_cerca e conversazione_cerca sono riservati (passano da last_private)", all(rr.values()), rr)


def prova_peso():
    """Bloccante 2 e il peso verso le pagine."""
    from calliope.brain import Brain, _tokens
    from calliope.conversazioni import CHAT_COPIE_PIENE, alleggerisci
    msg = {"role": "user", "content": "Mostrami la relazione"}
    prima = _tokens([msg, {"role": "assistant", "content": "Eccola."}])
    grosso = {**schede.documento_markdown("Relazione", "parola " * 1000, chiave="lavoro:L1")}
    b = brain_finto([msg])
    Brain._invia_schede(b, HubFinto(), [grosso, schede.calcolo("1+1", "2")], DARIO)
    dopo = _tokens([msg, {"role": "assistant", "content": "Eccola."}])
    verifica("la stima dei token resta quella di prima con le schede legate",
             "_schede" in msg and prima == dopo, (prima, dopo))
    turni_ = [{"id": i, "quando": float(i), "domanda": "d", "risposta": "r", "canale": "voce", "luogo": "",
               "schede": [{"tipo": "calcolo", "titolo": "Calcolo", "espressione": "1+1", "risultato": "2", "id": f"c{i}"}]}
              for i in range(CHAT_COPIE_PIENE + 3)]
    alleggerisci(turni_)
    verifica("alle pagine le copie intere solo negli ultimi turni con schede, prima leggere",
             all(t["schede"][0].get("leggera") and "risultato" not in t["schede"][0] for t in turni_[:3])
             and all("risultato" in t["schede"][0] for t in turni_[3:]), [t["schede"][0] for t in turni_[:4]])
    # Foto e file del turno: mai legati (partono prima della frase della persona)
    s = [{"role": "user", "content": "la frase di prima"}]
    bf = brain_finto(s)
    bf._send_cards = lambda cards, tool: Brain._invia_schede(bf, HubFinto(), cards, DARIO)
    foto = {"tipo": "foto", "titolo": "Foto", "src": "data:image/jpeg;base64,AA"}
    Brain.manda_schede(bf, [foto], "foto")
    verifica("le miniature di foto e file non si legano al turno di prima (dal 29/10 aspettano la frase: #272)",
             "_schede" not in s[0], s[0])
    # Il calcolo senza oscura, il timer senza «chi»
    from calliope.conversazione import turni
    calc = schede.per_conversazione(schede.calcolo("123456789 × 1000", "123456789000"))
    tim = schede.per_conversazione(schede.timer({"id": 1, "label": "pasta", "due": time.time() + 60,
                                                 "created": time.time(), "owner_name": "Bianca"}))
    tt = turni([{"role": "user", "content": "quanto fa?", "_schede": [calc, tim]}, {"role": "assistant", "content": "Fa così."}])
    sc = tt[0]["meta"]["schede"]
    verifica("il risultato di un calcolo grande resta (oscura non lo nasconde)",
             sc[0]["risultato"] == "123456789000", sc[0])
    verifica("la copia del timer senza chi l'ha messo", "chi" not in sc[1]["timer"][0], sc[1])
    verifica("avviso non è fra i rimandi", schede.per_conversazione({"tipo": "avviso", "titolo": "x"}) is None)


def prova_dettaglio(arch):
    """Il dettaglio di una scheda leggera: solo dai turni del proprietario."""
    from calliope.conversazione import Conversazione, turni
    c = Conversazione("persona:dario")
    msg = []
    for i in range(14):
        msg += [{"role": "user", "content": f"conto {i}", "_turno": {"t": time.time() - 3000 + i},
                 "_schede": [schede.per_conversazione(schede.calcolo(f"{i}+1", str(i + 1)))]},
                {"role": "assistant", "content": str(i + 1)}]
    arch.archivia(c, turni(msg), "dario", "Dario", ospite=False)
    ch = arch.chat("dario")
    leggere = [t for t in ch if t.get("schede") and t["schede"][0].get("leggera")]
    verifica("benvenuto: le schede dei turni vecchi leggere", len(leggere) >= 2, len(leggere))
    t0 = leggere[0]
    piena = arch.chat_scheda("dario", t0["id"], 0)
    verifica("il dettaglio dà la copia intera del suo turno",
             piena and piena["tipo"] == t0["schede"][0]["tipo"] and piena.get("storica")
             and not piena.get("leggera") and len(piena) > len(t0["schede"][0]), piena)
    verifica("…mai da un turno d'un'altra persona", arch.chat_scheda("bianca", t0["id"], 0) is None
             and arch.chat_scheda("dario", t0["id"], 3) is None)
    return t0["id"], t0["schede"][0]["tipo"]


def prova_dettaglio_server(arch, tid_tipo):
    tid, tipo = tid_tipo
    from calliope.schermi.server import ServerSchermi
    hub = Schermi(cfg_prova(), ArchivioSchermi(str(TMP / "dettaglio.db")), log=lambda m: None)
    hub.chat_fonte = arch
    srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
    hub.server = srv
    c = httpx.Client(base_url=f"http://127.0.0.1:{srv.port}", timeout=5)
    _, tok_d = hub.archivio.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario")
    _, tok_b = hub.archivio.crea_con_token("camera", proprietario="bianca", proprietario_nome="Bianca")
    _, tok_s = hub.archivio.crea_con_token("cucina")
    hub._rinfresca()

    def h(t):
        return {"X-Calliope-Sessione": c.post("/api/accedi", headers={"Authorization": f"Bearer {t}"}).json()["sessione"]}
    r = c.post("/api/conversazione", headers=h(tok_d), json={"turno": tid, "indice": 0})
    verifica("/api/conversazione {turno, indice}: la copia intera dallo schermo di Dario",
             r.status_code == 200 and r.json()["scheda"]["tipo"] == tipo, r.text[:200])
    r = c.post("/api/conversazione", headers=h(tok_b), json={"turno": tid, "indice": 0})
    verifica("…dallo schermo di Bianca 404", r.status_code == 404, r.status_code)
    r = c.post("/api/conversazione", headers=h(tok_s), json={"turno": tid, "indice": 0})
    verifica("…da uno schermo di stanza 403", r.status_code == 403, r.status_code)
    stati = [c.post("/api/conversazione", headers=h(tok_d), json=x).status_code
             for x in ({"turno": "1", "indice": 0}, {"turno": tid, "indice": 9}, {"turno": True, "indice": 0})]
    verifica("…dati non validi 400", stati == [400, 400, 400], stati)
    srv.ferma()
    hub.archivio.close()
    c.close()


# ─────────────────────────── 7. foto e file nella Conversazione (29/10, #272) ───────────────────────────
def jpeg_vero(w=1280, h=960):
    """Una foto da telefono, con dettagli (una tinta unita si comprime troppo)."""
    import io
    import random
    from PIL import Image
    random.seed(7)
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            c = (random.randrange(256), (x * 3) % 256, (y * 5) % 256)
            for dy in range(4):
                for dx in range(4):
                    px[x + dx, y + dy] = c
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


class HubMittente(HubFinto):
    """Come HubFinto, con chi parla adesso (hub.mittente del contesto dei tool)."""

    def __init__(self, chi):
        super().__init__()
        self.chi = chi

    def mittente(self, ctx):
        return self.chi


def brain_foto(storia, hub):
    from calliope.brain import Brain
    b = brain_finto(storia)
    b.tool_ctx = SimpleNamespace(schermi=hub)
    b.ATTESA_SCHEDE_S = Brain.ATTESA_SCHEDE_S
    b._in_attesa = lambda c, p: Brain._in_attesa(b, c, p)
    b._lega_in_attesa = lambda m: Brain._lega_in_attesa(b, m)
    b._send_cards = lambda cards, tool: Brain._invia_schede(b, hub, cards, hub.chi)
    return b


def prova_foto():
    from calliope.brain import Brain
    from calliope.conversazione import turni
    from calliope.immagini import Immagine
    jpeg = jpeg_vero()
    img = Immagine(jpeg, 1280, 960, fonte="telefono", persona="dario", n=1)
    card = schede.foto(img, "lo scontrino")
    copia = schede.per_conversazione(card)
    peso = len(json.dumps(copia, ensure_ascii=False))
    verifica("foto: la copia con la miniatura piccola, dentro gli 8 kB, mai la miniatura dello schermo né il file",
             copia and copia.get("storica") and copia["src"].startswith("data:image/jpeg;base64,")
             and copia["src"] != card["src"] and peso <= schede.CONV_SCHEDA_MAX and "_mini" not in copia
             and len(card["src"]) > len(copia["src"]), (peso, len(card["src"])))
    grossa = {**card, "_mini": "data:image/jpeg;base64," + "A" * 9000}
    r = schede.per_conversazione(grossa)
    verifica("foto: una miniatura oltre il tetto diventa il solo rimando, senza i byte",
             r and r.get("rimando") and "src" not in r, r)
    from calliope.allegati import Allegato  # noqa: F401 — la scheda del file si costruisce a mano
    fil = schede.nuova("allegato", "File 1", schede.PERSONALE, chiave="allegato:1", nome="bolletta.pdf",
                       tipo_file="PDF", categoria="documento", dimensione="120 kB",
                       note=["3 pagine"], anteprima="Importo da pagare 84,20 euro")
    r = schede.per_conversazione(fil)
    verifica("file: nome, tipo e dimensione, mai l'anteprima del testo né le note",
             r and r.get("nome") == "bolletta.pdf" and "anteprima" not in r and "note" not in r, r)

    # 1. La foto mandata con la frase: la miniatura parte prima, si lega alla frase quando entra
    hub = HubMittente(DARIO)
    storia = [{"role": "user", "content": "la frase di prima"}, {"role": "assistant", "content": "ok"}]
    b = brain_foto(storia, hub)
    Brain.manda_schede(b, [schede.foto(img)], "foto")
    msg = {"role": "user", "content": "Quanto ho speso in tutto?"}
    storia.append(msg)
    Brain._lega_in_attesa(b, msg)
    verifica("foto con la frase: legata alla frase di questo turno, non a quella di prima",
             "_schede" not in storia[0] and [x["tipo"] for x in msg.get("_schede", [])] == ["foto"]
             and msg["_schede"][0].get("src", "").startswith("data:image/jpeg"), msg.get("_schede"))
    # 2. La foto mandata prima della frase (in attesa per immagini_attesa_s): il ciclo la mette nel
    # turno della frase dopo (Ciclo._foto_e_file) e la miniatura parte con quel turno, come la 1
    storia2 = [{"role": "user", "content": "di prima"}]
    b2 = brain_foto(storia2, HubMittente(DARIO))
    img2 = Immagine(jpeg, 1280, 960, fonte="telefono", persona="dario", arrivata=time.time() - 40, n=2)
    Brain.manda_schede(b2, [schede.foto(img2)], "foto")
    msg2 = {"role": "user", "content": "Cosa c'è in questa foto?"}
    storia2.append(msg2)
    Brain._lega_in_attesa(b2, msg2)
    verifica("foto mandata prima della frase: legata alla frase che la usa",
             "_schede" not in storia2[0] and len(msg2.get("_schede", [])) == 1)
    # …e una scheda in attesa che parte quando la frase è già entrata (le trattenute di un minore)
    Brain._invia_schede(b2, b2.tool_ctx.schermi, [{**schede.foto(Immagine(jpeg, 1280, 960, persona="dario", n=4)), "_attesa": True}], DARIO)
    verifica("…una miniatura che parte dopo la frase va alla stessa frase", len(msg2.get("_schede", [])) == 2)
    # 3. La cattura della webcam chiesta a voce: la scheda del tool, dentro la risposta
    storia3 = [{"role": "user", "content": "Guarda dalla webcam"}]
    b3 = brain_foto(storia3, HubMittente(DARIO))
    cam = Immagine(jpeg, 1280, 960, fonte="webcam", persona="dario", n=3)
    Brain._invia_schede(b3, b3.tool_ctx.schermi, [schede.foto(cam)], DARIO)
    verifica("cattura della webcam chiesta a voce: legata alla frase che l'ha chiesta",
             [x["tipo"] for x in storia3[0].get("_schede", [])] == ["foto"])
    # Decisione 0034 (28/10): anche webcam e schermate restano con la miniatura
    shot = Immagine(jpeg, 1280, 960, fonte="screenshot", persona="dario", n=5)
    Brain._invia_schede(b3, b3.tool_ctx.schermi, [schede.foto(shot)], DARIO)
    fonti = [(x.get("fonte"), str(x.get("src", ""))[:23]) for x in storia3[0].get("_schede", [])]
    verifica("webcam e schermata (decisione 0034): legate con la loro miniatura",
             len(fonti) == 2 and all(f[1] == "data:image/jpeg;base64," for f in fonti), fonti)
    # «mostrami l'ultima» dopo: la scheda ricordata non è più in attesa
    s8 = [{"role": "user", "content": "di prima"}]
    b8 = brain_foto(s8, HubMittente(DARIO))
    c8 = schede.foto(Immagine(jpeg, 1280, 960, persona="dario", n=6))
    Brain.manda_schede(b8, [c8], "foto")
    verifica("il segno _attesa vale per un invio solo (hub.ricorda tiene lo stesso dizionario)", "_attesa" not in c8)
    # 4. Cambio di persona in mezzo: la miniatura di Dario non va alla frase di Bianca
    storia4 = [{"role": "user", "content": "di Dario"}]
    hub4 = HubMittente(DARIO)
    b4 = brain_foto(storia4, hub4)
    Brain.manda_schede(b4, [schede.foto(img)], "foto")
    hub4.chi = Mittente("bianca", "Bianca", "familiare", True)
    msg4 = {"role": "user", "content": "Sono Bianca"}
    storia4.append(msg4)
    Brain._lega_in_attesa(b4, msg4)
    verifica("cambio di chi parla in mezzo: la miniatura non va all'altra persona, e si butta",
             "_schede" not in msg4 and "_schede" not in storia4[0] and not b4.__dict__.get("_schede_attesa"))
    # …né a una frase che arriva troppo tardi (un'altra corsia ha risposto)
    storia4b = [{"role": "user", "content": "di prima"}]
    b4b = brain_foto(storia4b, HubMittente(DARIO))
    Brain.manda_schede(b4b, [schede.foto(img)], "foto")
    b4b.__dict__["_schede_attesa"] = [(time.monotonic() - 600, "dario", x[2]) for x in b4b.__dict__["_schede_attesa"]]
    msg4b = {"role": "user", "content": "molto dopo"}
    storia4b.append(msg4b)
    Brain._lega_in_attesa(b4b, msg4b)
    verifica("…né a una frase di molto dopo", "_schede" not in msg4b)
    # 5. Identità incerta: niente
    storia5 = [{"role": "user", "content": "di prima"}]
    hub5 = HubMittente(GRIGIA)
    b5 = brain_foto(storia5, hub5)
    Brain.manda_schede(b5, [schede.foto(img)], "foto")
    msg5 = {"role": "user", "content": "frase dalla zona grigia"}
    storia5.append(msg5)
    Brain._lega_in_attesa(b5, msg5)
    verifica("identità incerta: la miniatura non si lega", "_schede" not in msg5 and not hub5.inviate[0].get("_riservata"))
    # 6. Turno riservato: la foto legata sparisce con le schede del turno
    msg6 = {"role": "user", "content": "Leggi il contratto in foto", "_schede": [schede.per_conversazione(schede.foto(img))]}
    tt = turni([msg6, {"role": "tool", "name": "archivio_cerca", "content": "{}"},
                {"role": "assistant", "content": "Canone 850."}], frozenset({"archivio_cerca"}))
    verifica("turno riservato: la miniatura non resta nell'archivio", "schede" not in (tt[0].get("meta") or {}), tt[0])
    # La risposta di prima riservata non tiene fuori la foto di adesso (last_private è ancora quello)
    storia7 = [{"role": "user", "content": "di prima"}]
    b7 = brain_foto(storia7, HubMittente(DARIO))
    b7.last_private = True
    Brain.manda_schede(b7, [schede.foto(img)], "foto")
    msg7 = {"role": "user", "content": "e questa?"}
    storia7.append(msg7)
    Brain._lega_in_attesa(b7, msg7)
    verifica("una risposta riservata prima non tiene fuori la foto di questo turno", len(msg7.get("_schede", [])) == 1)


# ─────────────────────────── 8. la foto tenuta (29/10, decisione 0034) ───────────────────────────
class Orologio:
    def __init__(self):
        self.t = time.time()

    def __call__(self):
        return self.t


def cassetto_prova(nome):
    from calliope.cassetto import Cassetto
    cas = Cassetto(str(TMP / f"{nome}.db"), str(TMP / f"cassetto-{nome}"), giorni=7, giorni_foto=60,
                   log=lambda m: None)
    cas.ora = Orologio()
    cas.archivio = SimpleNamespace(cartella=str(TMP / f"archivio-{nome}"), sveglia=lambda: None)
    return cas


def ctx_foto(cas, prof, modo="voce"):
    return SimpleNamespace(cassetto=cas, archivio=cas.archivio, immagini=None, schermi=None,
                           cfg=SimpleNamespace(immagini_tenuta=True, immagini_lato_max=1280),
                           speaker_ctx=SimpleNamespace(current_speaker=getattr(prof, "name", None),
                                                       identified_by=modo, from_session=False,
                                                       current_level="familiare" if prof else "ospite"),
                           speakers={prof.name: prof} if prof else None)


def prova_foto_tenute():
    from calliope.config import Config
    from calliope.cassetto import giorni_foto
    from calliope.immagini import Immagine
    from calliope.tools import immagini as TI
    c = Config()
    verifica("configurazione: la tenuta accesa di serie, 60 giorni; spenta come prima",
             giorni_foto(c) == 60.0 and giorni_foto(SimpleNamespace(immagini_tenuta=False)) is None)
    dario = SimpleNamespace(id="dario", name="Dario")
    jpeg = jpeg_vero(800, 600)
    # 1. Tenuta 60 giorni, poi via
    cas = cassetto_prova("t1")
    img = Immagine(jpeg, 800, 600, fonte="telefono", persona="dario", n=1)
    fid = cas.metti_foto(img, "dario")
    st = cas.stato_foto("dario", fid)
    verifica("la foto intera tenuta 60 giorni, e la foto sa dov'è la sua copia",
             img.cassetto == fid and st["stato"] == "tenuta" and st["jpeg"] == jpeg
             and abs(st["scade"] - cas.ora() - 60 * 86400) < 5, {k: v for k, v in st.items() if k != "jpeg"})
    copia = schede.per_conversazione(schede.foto(img))
    verifica("la miniatura del turno porta l'id della copia", copia.get("cassetto") == fid, copia.get("cassetto"))
    cas.ora.t += 59 * 86400
    cas.pulisci()
    verifica("dopo 59 giorni c'è ancora", cas.stato_foto("dario", fid)["stato"] == "tenuta")
    cas.ora.t += 2 * 86400
    cas.pulisci()
    verifica("dopo 61 giorni non c'è più, e il file è tolto",
             cas.stato_foto("dario", fid) == {"stato": "persa"}
             and not list((TMP / "cassetto-t1").rglob("*.dat")))
    verifica("la foto d'un'altra persona risponde come un id che non c'è («persa»)",
             cas.stato_foto("bianca", fid) == {"stato": "persa"} == cas.stato_foto("dario", 999))
    # 2. «archiviala» su una foto di tre giorni prima, ancora tenuta
    cas2 = cassetto_prova("t2")
    vecchia = Immagine(jpeg, 800, 600, persona="dario", n=1, arrivata=cas2.ora() - 3 * 86400)
    cas2.ora.t -= 3 * 86400
    fid2 = cas2.metti_foto(vecchia, "dario")
    cas2.ora.t += 3 * 86400
    # Dalla zona grigia, con la frase breve o da ospite: rifiutato, senza dire niente delle foto
    cas2.metti_foto(Immagine(jpeg, 800, 600, persona="dario", n=2), "dario")
    for modo in ("conversazione", "breve"):
        r = TI._archivia(ctx_foto(cas2, dario, modo), quale="oggi")
        testo = json.dumps(r, ensure_ascii=False)
        verifica(f"«archiviala» con quale dalla {modo}: rifiutato, la foto resta tenuta, niente nomi né date",
                 not r.get("ok") and cas2.stato_foto("dario", fid2)["stato"] == "tenuta"
                 and "Foto " not in testo and "C" + str(fid2) not in testo and "foto" not in r, r)
    r = TI._archivia(ctx_foto(cas2, None), quale="oggi")
    verifica("…e da ospite", not r.get("ok") and not list(Path(cas2.archivio.cartella).rglob("*.jpg")), r)
    r = TI._archivia(ctx_foto(cas2, dario), quale=f"C{fid2}")
    archiviate = list(Path(cas2.archivio.cartella).rglob("*.jpg"))
    verifica("«archiviala» su una foto di giorni prima: per sempre nei documenti",
             r.get("ok") and len(archiviate) == 1 and cas2.stato_foto("dario", fid2) == {"stato": "archiviata"}, r)
    cas2.ora.t += 120 * 86400
    cas2.pulisci()
    verifica("…e dopo mesi la Conversazione dice ancora «Archiviata.»",
             cas2.stato_foto("dario", fid2) == {"stato": "archiviata"} and archiviate[0].exists())
    # «archivia la foto di martedì» per giorno; l'ultima della conversazione con la sua copia
    cas3 = cassetto_prova("t3")
    album = SimpleNamespace(prendi=lambda n: img3, __len__=lambda: 1)
    img3 = Immagine(jpeg, 800, 600, persona="dario", n=1)
    fid3 = cas3.metti_foto(img3, "dario")
    ctx3 = ctx_foto(cas3, dario)
    ctx3.immagini = SimpleNamespace(prendi=lambda n: img3, numeri=lambda: [1])
    # Senza `quale`, sulla foto di questa conversazione (decisione del 29/10, cambia il 05/10):
    # zona grigia, frase breve e ospite col rifiuto generico; con la voce come prima
    for modo in ("conversazione", "breve"):
        cx = ctx_foto(cas3, dario, modo)
        cx.immagini = ctx3.immagini
        r = TI._archivia(cx, foto=-1)
        verifica(f"«archiviala» sulla foto della conversazione dalla {modo}: rifiutato, niente archiviato",
                 not r.get("ok") and "riconoscere bene la tua voce" in r["risposta_finale"]
                 and cas3.stato_foto("dario", fid3)["stato"] == "tenuta"
                 and not list(Path(cas3.archivio.cartella).rglob("*.jpg")), r)
    cx = ctx_foto(cas3, None)
    cx.immagini = ctx3.immagini
    r = TI._archivia(cx, foto=-1)
    verifica("…e da ospite", not r.get("ok") and "solo per chi riconosco" in r["risposta_finale"]
             and not list(Path(cas3.archivio.cartella).rglob("*.jpg")), r)
    cx = ctx_foto(cas3, dario, "schermo")
    cx.immagini = ctx3.immagini
    cx.cassetto = None
    r = TI._archivia(cx, foto=-1)
    verifica("…dallo schermo personale sì (anche senza cassetto, come prima)", r.get("ok"), r)
    for f in Path(cas3.archivio.cartella).rglob("*.jpg"):
        f.unlink()
    r = TI._archivia(ctx3, foto=-1)
    verifica("«archiviala» sulla foto della conversazione archivia la sua copia (stato «Archiviata.»)",
             r.get("ok") and cas3.stato_foto("dario", fid3) == {"stato": "archiviata"}, r)
    cas4 = cassetto_prova("t4")
    cas4.metti_foto(Immagine(jpeg, 800, 600, persona="dario", n=1), "dario")
    r = TI._archivia(ctx_foto(cas4, dario), quale="la foto di oggi")
    verifica("«archivia la foto di oggi» la trova fra quelle tenute", r.get("ok"), r)
    # 3. Un ospite non si tiene mai; 4. l'identità incerta nemmeno
    cas5 = cassetto_prova("t5")
    TI._tieni_cattura(ctx_foto(cas5, None), Immagine(jpeg, 800, 600, fonte="webcam", n=1), None)
    verifica("un ospite: la cattura non si tiene", cas5.elenco("dario") == [] and not list((TMP / "cassetto-t5").rglob("*.dat")))
    for modo in ("breve", "conversazione", "schermo"):
        r = TI._pc_guarda(ctx_foto(cas5, dario, modo), "webcam")
        verifica(f"identità incerta ({modo}): pc_guarda non cattura e non tiene niente",
                 not r.get("ok") and cas5.elenco("dario") == [], r.get("risposta_finale"))
    TI._tieni_cattura(ctx_foto(cas5, dario), Immagine(jpeg, 800, 600, fonte="screenshot", n=2), dario)
    verifica("la cattura chiesta a voce si tiene (decisione 0034)",
             [r["fonte"] for r in cas5.elenco("dario")] == ["screenshot"])
    # 5. «dimentica» e svuota tolgono anche i file
    from calliope.conserva import Conservazione
    from calliope.conversazioni import ArchivioConversazioni
    cas6 = cassetto_prova("t6")
    a = cas6.metti_foto(Immagine(jpeg, 800, 600, n=1), "dario")
    b = cas6.metti_foto(Immagine(jpeg, 800, 600, n=2), "bianca")
    arch = ArchivioConversazioni(TMP / "dim.db", giorni=60, avvia=False, log=lambda m: None)
    arch.su_dimentica.append(cas6.dimentica_foto)
    arch.dimentica("dario")
    verifica("«dimentica le nostre conversazioni» toglie anche le foto tenute (file e righe), solo sue",
             cas6.stato_foto("dario", a) == {"stato": "persa"} and cas6.stato_foto("bianca", b)["stato"] == "tenuta"
             and len(list((TMP / "cassetto-t6").rglob("*.dat"))) == 1)
    arch.close()
    finto = SimpleNamespace(cassetto=cas6, cfg=None, log=lambda m: None)
    n = Conservazione._svuota_foto(finto, None)
    verifica("`calliope conserva --svuota` toglie tutte le foto tenute",
             n == 1 and not list((TMP / "cassetto-t6").rglob("*.dat")), n)
    return cas


def prova_foto_server():
    """La foto intera e il suo stato dal dettaglio: solo il proprietario, dallo schermo personale."""
    from calliope.immagini import Immagine
    from calliope.schermi.server import ServerSchermi
    cas = cassetto_prova("srv")
    jpeg = jpeg_vero(800, 600)
    fid = cas.metti_foto(Immagine(jpeg, 800, 600, n=1), "dario")
    hub = Schermi(cfg_prova(), ArchivioSchermi(str(TMP / "foto-srv.db")), log=lambda m: None)
    hub.cassetto = cas
    srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
    hub.server = srv
    c = httpx.Client(base_url=f"http://127.0.0.1:{srv.port}", timeout=5)
    _, tok_d = hub.archivio.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario")
    _, tok_b = hub.archivio.crea_con_token("camera", proprietario="bianca", proprietario_nome="Bianca")
    _, tok_s = hub.archivio.crea_con_token("cucina")
    hub._rinfresca()

    def h(t):
        return {"X-Calliope-Sessione": c.post("/api/accedi", headers={"Authorization": f"Bearer {t}"}).json()["sessione"]}
    import base64
    r = c.post("/api/conversazione", headers=h(tok_d), json={"foto": fid})
    d = r.json()
    intera = c.get(d["url"]) if d.get("url") else None
    verifica("{foto}: dallo schermo di Dario lo stato e la foto intera, da «Scarica» (un gettone)",
             r.status_code == 200 and d["stato"] == "tenuta" and d.get("scade") and "src" not in d
             and d["url"].startswith("/scarica/") and intera is not None and intera.content == jpeg,
             {k: str(v)[:40] for k, v in d.items()})
    verifica("…il gettone vale per poche richieste", [c.get(d["url"]).status_code for _ in range(3)][-1] != 200)
    cas.ora.t += 61 * 86400
    cas.pulisci()
    r2 = c.post("/api/conversazione", headers=h(tok_d), json={"foto": fid})
    verifica("…scaduta: «persa», senza foto", r2.json() == {"stato": "persa"}, r2.text)
    cas.ora.t -= 61 * 86400
    r = c.post("/api/conversazione", headers=h(tok_b), json={"foto": fid})
    r9 = c.post("/api/conversazione", headers=h(tok_b), json={"foto": 99999})
    verifica("…dallo schermo di Bianca «persa», senza foto, come un id che non c'è",
             r.status_code == 200 and r.json() == {"stato": "persa"} == r9.json(), (r.status_code, r.text))
    r = c.post("/api/conversazione", headers=h(tok_s), json={"foto": fid})
    verifica("…da uno schermo di stanza 403", r.status_code == 403, r.status_code)
    r = c.post("/api/conversazione", headers={"X-Calliope-Sessione": "falsa"}, json={"foto": fid})
    verifica("…senza sessione 401", r.status_code == 401, r.status_code)
    stati = [c.post("/api/conversazione", headers=h(tok_d), json={"foto": x}).status_code for x in ("1", True, -1)]
    verifica("…dati non validi 400", stati == [400, 400, 400], stati)
    srv.ferma()
    hub.archivio.close()
    c.close()


def prova_foto_revisione():
    """Seconda revisione della PR #273: la revisione del cassetto per le foto, «dimentica» detto."""
    from calliope.immagini import Immagine
    from calliope.tools import conversazioni as TC
    cas = cassetto_prova("rev")
    jpeg = jpeg_vero(400, 300)
    cas.metti_foto(Immagine(jpeg, 400, 300, n=1), "dario")
    cas.metti(  # un PDF che scade domani
        "dario", b"%PDF-1.4 prova", "bolletta.pdf", "pdf", giorni=1)
    cas.ora.t += 59 * 86400
    info = cas.da_dire("dario")
    con = cas.frase(info, True)
    senza = cas.frase(info, False)
    verifica("revisione con lo schermo aperto: la foto in scadenza solo nella scheda, a voce gli altri file",
             len(info["in_scadenza"]) == 2 and con.startswith("Hai un file che scade") and "foto" not in con
             and "Hai 2 file" in senza, (con, senza))
    cas.ora.t += 2 * 86400
    cas.pulisci()
    info = cas.da_dire("dario")
    verifica("le foto scadute non si annunciano, gli altri file sì",
             info["eliminati"] == 1 and "un file" in cas.frase(info, True), (info, cas.frase(info, True)))
    cas2 = cassetto_prova("rev2")
    cas2.metti_foto(Immagine(jpeg, 400, 300, n=1), "dario")
    cas2.ora.t += 59 * 86400
    senza = cas2.frase(cas2.da_dire("dario"), False)
    verifica("…senza schermo la foto in scadenza resta detta a voce", "una foto" in senza, senza)
    # «dimentica» lo dice
    from calliope.conversazioni import ArchivioConversazioni
    arch = ArchivioConversazioni(TMP / "dim2.db", giorni=60, avvia=False, log=lambda m: None)
    ctx = SimpleNamespace(conversazioni=arch, cassetto=cas2, turno=5, stanza=None,
                          speaker_ctx=SimpleNamespace(current_speaker="Dario"),
                          speakers={"Dario": SimpleNamespace(id="dario", name="Dario")})
    TC._conversazioni_dimentica(ctx)
    ctx.turno = 6
    r = TC._conversazioni_dimentica(ctx)
    verifica("«dimentica»: la risposta dice che le foto archiviate restano nei documenti",
             r.get("ok", True) is not False and TC.FOTO_ARCHIVIATE_RESTANO in r["risposta_finale"], r)
    arch.close()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        prova_per_conversazione()
        prova_brain()
        prova_turni()
        prova_modulo()
        prova_modulo_riservato()
        arch = archivio_pieno()
        prova_filtri(arch)
        prova_server(arch)
        prova_riservato()
        prova_peso()
        prova_foto()
        prova_foto_tenute()
        prova_foto_server()
        prova_foto_revisione()
        tid = prova_dettaglio(arch)
        prova_dettaglio_server(arch, tid)
        arch.close()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
