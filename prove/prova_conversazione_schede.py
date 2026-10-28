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
  con Retry-After.

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
    b.lega_scheda_al_turno = lambda c: Brain.lega_scheda_al_turno(b, c)
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
        arch = archivio_pieno()
        prova_filtri(arch)
        prova_server(arch)
        arch.close()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
