import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della cronologia delle schede per persona e della scheda «Conversazione»
(08/10/2026, calliope/schermi/cronologia.py, calliope/conversazioni.py).

- salvataggio: solo le schede personali di chi è riconosciuto con certezza (mai ospiti, zona
  grigia, schede di stanza o della casa), anche senza uno schermo personale collegato; chiavi
  uniche che sostituiscono (al loro posto con `sposta: false`); tenuta in giorni, tetto in
  numero e in byte; file per persona (permessi 600 fuori da Windows), riscritto da un thread;
- ripresa dopo un «riavvio» (hub e cronologia nuovi sulla stessa cartella): uno schermo
  personale nuovo ritrova le ultime N schede in ordine, mai quelle di un'altra persona (né un
  minore quelle del tutore, né il tutore quelle del minore), mai uno schermo di stanza;
- schede finali: modulo chiuso e timer finito saltati, avanzamento di un lavoro interrotto →
  «interrotto» senza il flusso, esercizi chiusi → riepilogo, sviluppo ricostruito dallo stato
  vero (anche se non era tra le ultime), programma che girava → fermato, cassetto con i soli
  file che ci sono ancora, chiavi delle foto di un avvio di prima che non si confondono;
- «Scarica»: registrato di nuovo per lo schermo nuovo (gettone nuovo; quello di prima non vale);
- pulizia: «schede_pulisci» (solo le sue, mai dalla zona grigia), POST /api/schede (solo da uno
  schermo personale), evento «pulisci» alle pagine, file tolto, lo sviluppo aperto resta;
- conversazione: archivio con `meta` (migrazione dalla versione 1), turni in diretta solo agli
  schermi personali della persona (mai ospiti né altri), ricaricati nel benvenuto, frase di
  sfida e codici tolti, segreti del turno tolti, «dimentica» che svuota, tenuta, «Scarica» in
  Markdown, `_archivia_turno` del ciclo; server vero su 127.0.0.1 con SSE.

Tutto in una cartella temporanea. ~3 s.
"""

import asyncio
import json
import shutil
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx

from calliope.config import Config
from calliope.schermi import ArchivioSchermi, Mittente, Schermi, schede
from calliope.schermi.cronologia import CronologiaSchede, nome_file
from calliope.schermi.scarica import Rifiuto

TMP = Path(tempfile.mkdtemp(prefix="calliope-cronologia-"))
ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({str(dettaglio)[:300]})" if dettaglio else ""),
          flush=True)
    if not ok:
        ERRORI.append(nome)


def cfg_prova(**kw) -> Config:
    c = Config()
    c.memory_db = str(TMP / "memoria.db")
    c.config_dir = str(TMP)
    c.conversazioni_db = str(TMP / "conversazioni.db")
    for k, v in kw.items():
        setattr(c, k, v)
    return c


DARIO = Mittente("dario", "Dario", "amministra", True)
BIANCA = Mittente("bianca", "Bianca", "familiare", True)
TEO = Mittente("teo", "Teo", "familiare", True)          # un ragazzo: Dario ne è il tutore
GRIGIA = Mittente("dario", "Dario", "familiare", False)
OSPITE = Mittente()


def hub_nuovo(cartella, avvio=None, db="schermi.db"):
    cfg = cfg_prova()
    hub = Schermi(cfg, ArchivioSchermi(str(TMP / db)), log=lambda m: None)
    hub.cronologia = CronologiaSchede(cartella, giorni=7, massimo=40, mb=4.0,
                                      log=lambda m: None, avvio=avvio, scrivi_subito=True)
    return hub


class Conn:
    """Una pagina finta: le consegne del hub arrivano in un ciclo asyncio suo."""

    def __init__(self, hub, schermo, ripresa=None):
        self.loop = asyncio.new_event_loop()
        self.conn, self.storia = hub.collega(schermo, self.loop, ripresa=ripresa)

    def eventi(self):
        self.loop.run_until_complete(asyncio.sleep(0.01))
        out = []
        while not self.conn.coda.empty():
            out.append(self.conn.coda.get_nowait())
        return out


def chiavi(lst):
    return [c.get("chiave") or c.get("id") for c in lst]


# ─────────────────────────── 1. salvataggio e filtri ───────────────────────────
def prova_salvataggio():
    cart = TMP / "schede-1"
    hub = hub_nuovo(cart)
    arch = hub.archivio
    s_dario, _ = arch.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario")
    arch.crea_con_token("cucina")
    hub._rinfresca()
    doc = schede.documento_markdown("Relazione", "# Titolo\n\nTesto lungo.", chiave="lavoro:L1")
    hub.invia(doc, DARIO)
    hub.invia(schede.testo("Mio", "segreto mio", schede.PERSONALE), GRIGIA)
    hub.invia(schede.testo("Da ospite", "ciao", schede.PERSONALE), OSPITE)
    hub.invia(schede.calcolo("2+2", "4"), DARIO)                       # pubblica: di stanza
    hub.invia(schede.lista("spesa", ["pane"]), DARIO)                  # della casa
    v = hub.cronologia.ultime("dario")
    verifica("solo la scheda personale di chi è riconosciuto con certezza",
             chiavi([x["scheda"] for x in v]) == ["lavoro:L1"], chiavi([x["scheda"] for x in v]))
    verifica("la sorgente di «Scarica» resta sul server (nel file, non alle pagine)",
             "_scarica" in v[0]["scheda"] and "markdown" in v[0]["scheda"]["_scarica"])
    verifica("niente per gli ospiti", hub.cronologia.ultime("ospite") == [])
    # Bianca non ha schermi personali: la sua scheda si salva lo stesso
    r = hub.invia(schede.testo("Di Bianca", "x", schede.PERSONALE), BIANCA)
    verifica("senza schermi personali la scheda non va a nessuno ma resta nella cronologia",
             r["motivo"] == "personale" and len(hub.cronologia.ultime("bianca")) == 1, r)
    # Chiavi uniche: stessa chiave sostituisce; con sposta false resta al suo posto
    hub.invia(schede.testo("Altro", "y", schede.PERSONALE), DARIO)
    av = schede.lavoro_avanzamento("Relazione", "testo", "in_corso", {"passo": "scrive"},
                                   ident="L1")
    hub.invia(av, DARIO)
    v = [x["scheda"] for x in hub.cronologia.ultime("dario")]
    verifica("con la stessa chiave al suo posto (aggiornamento automatico)",
             chiavi(v)[0] == "lavoro:L1" and v[0].get("avanzamento") and len(v) == 2, chiavi(v))
    hub.invia(schede.documento_markdown("Relazione", "fine", chiave="lavoro:L1"), DARIO)
    v = [x["scheda"] for x in hub.cronologia.ultime("dario")]
    verifica("con la stessa chiave e `sposta` normale: in fondo, una sola",
             chiavi(v)[-1] == "lavoro:L1" and chiavi(v).count("lavoro:L1") == 1, chiavi(v))
    # Dallo schermo personale: invia_a (la risposta scritta da lì)
    hub.invia_a(s_dario["id"], schede.risposta("che ore sono", "Le dieci.", schede.PERSONALE,
                                                chiave="risposta:1"))
    v = [x["scheda"] for x in hub.cronologia.ultime("dario")]
    verifica("una scheda personale mandata a uno schermo personale: del suo proprietario",
             chiavi(v)[-1] == "risposta:1")
    p = cart / nome_file("dario")
    dati = json.loads(p.read_text(encoding="utf-8"))
    verifica("un file per persona, con la persona e le schede",
             dati["persona"] == "dario" and len(dati["schede"]) == 3)
    if os.name != "nt":
        verifica("permessi 600 al file e 700 alla cartella",
                 (p.stat().st_mode & 0o777) == 0o600 and (cart.stat().st_mode & 0o777) == 0o700)
    verifica("un id strano diventa un nome di file sicuro",
             nome_file("../x y") .startswith("p") and "/" not in nome_file("../x y"))
    # Tenuta e tetti
    c = CronologiaSchede(TMP / "schede-tetti", giorni=7, massimo=3, mb=4.0, log=lambda m: None,
                         scrivi_subito=True)
    for i in range(5):
        c.aggiungi("dario", schede.testo(f"T{i}", "x", schede.PERSONALE))
    verifica("tetto in numero: le più vecchie escono",
             [x["scheda"]["titolo"] for x in c.ultime("dario")] == ["T2", "T3", "T4"])
    c.ora = lambda: time.time() + 8 * 86400
    verifica("tenuta: dopo 7 giorni non c'è più", c.ultime("dario") == [])
    c2 = CronologiaSchede(TMP / "schede-mb", giorni=7, massimo=40, mb=0.01, log=lambda m: None,
                          scrivi_subito=True)
    for i in range(6):
        c2.aggiungi("dario", schede.testo(f"T{i}", "x" * 3000, schede.PERSONALE))
    n = len(c2.ultime("dario"))
    verifica("tetto in byte: restano le più nuove", 0 < n < 6
             and c2.ultime("dario")[-1]["scheda"]["titolo"] == "T5", n)
    # Con il thread di scrittura (come in Calliope): il file arriva un attimo dopo, la chiusura
    # scrive quello che manca
    c3 = CronologiaSchede(TMP / "schede-thread", log=lambda m: None)
    t0 = time.perf_counter()
    for i in range(50):
        c3.aggiungi("dario", schede.lavoro_avanzamento("L", "codice", "in_corso", {"passo": str(i)},
                                                       ident="L1"))
    ms = (time.perf_counter() - t0) * 1000 / 50
    f3 = TMP / "schede-thread" / nome_file("dario")
    verifica("aggiornamenti in diretta: niente disco nel thread di chi chiama (< 5 ms l'uno)",
             ms < 5 and not f3.exists(), f"{ms:.2f} ms")
    ok = False
    for _ in range(60):
        if f3.exists():
            ok = True
            break
        time.sleep(0.1)
    verifica("il thread scrive il file un attimo dopo, una scheda sola (stessa chiave)",
             ok and len(json.loads(f3.read_text(encoding="utf-8"))["schede"]) == 1)
    c3.aggiungi("dario", schede.testo("Ultima", "x", schede.PERSONALE))
    c3.close()
    verifica("alla chiusura scrive quello che manca",
             len(json.loads(f3.read_text(encoding="utf-8"))["schede"]) == 2)
    verifica("mai salvate: vuota, partite", not c.aggiungi("dario", schede.vuota())
             and not c.aggiungi("dario", schede.nuova("gioco", "G", schede.PERSONALE)))
    hub.archivio.close()


# ─────────────────────────── 2. ripresa dopo un riavvio ───────────────────────────
class Sessione:
    pass


def prova_ripresa():
    from calliope.sviluppo import Sviluppi, Sviluppo
    cart = TMP / "schede-2"
    hub = hub_nuovo(cart, avvio="primo", db="ripresa.db")
    arch = hub.archivio
    arch.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario")
    hub._rinfresca()
    # Le schede di prima del riavvio
    hub.invia(schede.documento_markdown("Relazione", "# R\n\nTesto.", chiave="lavoro:L1"), DARIO)
    hub.invia(schede.lavoro_avanzamento("Codice", "codice", "in_corso",
                                        {"passo": "scrive", "flusso": {
                                            "id": "f", "fino": 2, "pezzi": [
                                                {"n": 1, "s": 1, "t": "testo", "x": "a"},
                                                {"n": 2, "s": 1, "t": "testo", "x": "b"}]}},
                                        ident="L7", sposta=True), DARIO)
    hub.invia(schede.esecuzione("Prog", "p.py", "python", "in_corso", [], [], 0, None,
                                time.time(), 1.0, 60, ident="L7-1"), DARIO)
    hub.invia(schede.nuova("modulo", "Dati", schede.PERSONALE, modulo="m1", campi=[],
                           stato="aperto"), DARIO)
    hub.invia(schede.nuova("esercizio", "Esercizi: frazioni", schede.PERSONALE,
                           chiave="esercizi:dario", stato="aperta", domanda="1/2 + 1/4?",
                           esercizio="x", fatti=3, giuste=2), DARIO)
    hub.invia(schede.nuova("cassetto", "I tuoi file", schede.PERSONALE, chiave="cassetto:dario",
                           voci=[{"id": 1, "nome": "a.pdf"}, {"id": 2, "nome": "b.pdf"}]), DARIO)
    hub.invia(schede.nuova("foto", "Foto 1", schede.PERSONALE, chiave="foto:12345"), DARIO)
    hub.invia(schede.nuova("timer", "Timer", schede.PERSONALE, chiave="timer:1",
                           timer=[{"etichetta": "pasta", "fine": time.time() - 5}]), DARIO)
    # Teo (un ragazzo) ha le sue schede; Dario è suo tutore, ma non le vede da qui
    hub.invia(schede.testo("Compiti di Teo", "x", schede.PERSONALE), TEO)
    vecchio_gettone = None
    s_vecchio = hub.abbinati()[0]
    hub.registra_chat(s_vecchio["id"], "dario")
    try:
        vecchio_gettone = hub.scaricamenti.gettone(s_vecchio, "lavoro:L1", "md")["url"]
    except Rifiuto:
        pass
    hub.archivio.close()

    # «Riavvio»: hub e cronologia nuovi, stessa cartella; uno schermo personale nuovo
    cfg = cfg_prova(schermi_cronologia=12)
    hub2 = Schermi(cfg, ArchivioSchermi(str(TMP / "ripresa2.db")), log=lambda m: None)
    hub2.cronologia = CronologiaSchede(cart, avvio="secondo", log=lambda m: None,
                                       scrivi_subito=True)
    svs = Sviluppi(cfg, TMP / "sviluppi", log=lambda m: None)
    sv = Sviluppo(id="S3", persona="dario", persona_nome="Dario", titolo="Meteo",
                  aperta=time.time(), ultimo=time.time())
    svs.sviluppi.append(sv)
    hub2.lavori = SimpleNamespace(lavori=[SimpleNamespace(id="L7", stato="interrotto")],
                                  sviluppi=svs)
    hub2.ricostruttori.append(lambda p: [svs.scheda(x) for x in [svs.corrente(p)] if x])
    hub2.esercizi = SimpleNamespace(sessione=lambda p: None)
    hub2.cassetto = SimpleNamespace(proprietario=lambda i: "dario" if i == 2 else None)
    s_tel, _ = hub2.archivio.crea_con_token("telefono", proprietario="dario",
                                            proprietario_nome="Dario")
    s_teo, _ = hub2.archivio.crea_con_token("cameretta", proprietario="teo",
                                            proprietario_nome="Teo")
    s_cucina, _ = hub2.archivio.crea_con_token("cucina")
    hub2._rinfresca()
    rip = hub2.ripresa(s_tel)
    pagina = Conn(hub2, s_tel, ripresa=rip)
    st = pagina.storia
    tipi = [c["tipo"] for c in st]
    verifica("lo schermo personale nuovo ritrova le schede, in ordine, con lo sviluppo in fondo",
             tipi == ["documento", "lavoro", "esecuzione", "esercizio", "cassetto", "foto",
                      "sviluppo"], tipi)
    verifica("mai le schede di un'altra persona (nemmeno del ragazzo di cui è tutore)",
             not any("Teo" in c.get("titolo", "") for c in st))
    verifica("niente chiavi private alla pagina", not any(k.startswith("_") for c in st
                                                          for k in c))
    lav = next(c for c in st if c["tipo"] == "lavoro")
    verifica("avanzamento di un lavoro interrotto dal riavvio → scheda finale senza flusso",
             lav["stato"] == "interrotto" and "flusso" not in lav["avanzamento"]
             and "riavvio" in lav["riassunto"], lav.get("stato"))
    es = next(c for c in st if c["tipo"] == "esecuzione")
    verifica("un programma che girava prima del riavvio: fermato",
             es["stato"] == "fermato" and es["dal"] is None)
    ese = next(c for c in st if c["tipo"] == "esercizio")
    verifica("esercizi chiusi: il riepilogo, senza la domanda",
             ese["stato"] == "finita" and "domanda" not in ese and ese["fatti"] == 3)
    cas = next(c for c in st if c["tipo"] == "cassetto")
    verifica("cassetto: solo i file che ci sono ancora", [v["id"] for v in cas["voci"]] == [2])
    verifica("modulo chiuso e timer finito: saltati",
             "modulo" not in tipi and "timer" not in tipi)
    foto = next(c for c in st if c["tipo"] == "foto")
    verifica("la chiave di una foto di un avvio di prima non si confonde con una nuova",
             foto["chiave"] == "foto:12345@primo", foto["chiave"])
    svil = next(c for c in st if c["tipo"] == "sviluppo")
    verifica("lo sviluppo aperto si ricostruisce dallo stato vero (la vista torna subito)",
             svil["sviluppo"]["stato"] == "aperta" and svil["sviluppo"]["id"] == "S3")
    # «Scarica»: gettone nuovo per lo schermo nuovo, quello di prima non vale
    try:
        g = hub2.scaricamenti.gettone(s_tel, "lavoro:L1", "md")
        nome, tipo, dati = hub2.scaricamenti.prendi(g["url"].rsplit("/", 1)[1], hub2.valido)
        ok = dati.decode("utf-8").startswith("# R")
    except Rifiuto as e:
        ok = False
        g = e.frase
    verifica("«Scarica» dopo il riavvio: registrato per lo schermo nuovo, gettone nuovo", ok, g)
    vecchio = False
    try:
        hub2.scaricamenti.prendi((vecchio_gettone or "x/y").rsplit("/", 1)[1], hub2.valido)
    except Rifiuto:
        vecchio = True
    verifica("il gettone di prima del riavvio non vale più", bool(vecchio_gettone) and vecchio)
    # Il ragazzo vede le sue, uno schermo di stanza niente
    verifica("il ragazzo ritrova le sue schede sul suo schermo",
             [c["titolo"] for c in hub2.ripresa(s_teo)] == ["Compiti di Teo"])
    verifica("uno schermo di stanza non riceve niente dalla cronologia delle persone",
             hub2.ripresa(s_cucina) == [])
    # N: schermi_cronologia
    hub2.cfg.schermi_cronologia = 3
    verifica("riceve al più `schermi_cronologia` schede (le ultime)",
             len(hub2.ripresa(s_tel)) == 3 and hub2.ripresa(s_tel)[-1]["tipo"] == "sviluppo")
    # Uno schermo personale reso condiviso non rimanda le schede personali che aveva in memoria
    with hub2._lock:
        hub2._in_storia(s_cucina["id"], schede.testo("Vecchia personale", "x", schede.PERSONALE))
        hub2._in_storia(s_cucina["id"], schede.calcolo("1+1", "2"))
    st_c = Conn(hub2, s_cucina).storia
    verifica("schermo di stanza (reso condiviso): mai le schede personali rimaste in memoria",
             [c["tipo"] for c in st_c] == ["calcolo"], [c["tipo"] for c in st_c])
    # Ricollegata: le schede che lo schermo ha già non si ripetono
    pagina2 = Conn(hub2, s_tel, ripresa=hub2.ripresa(s_tel))
    k = chiavi(pagina2.storia)
    verifica("ricollegato: nessun doppione", len(k) == len(set(k)), k)
    return hub2, s_tel, pagina, svs


# ─────────────────────────── 3. pulizia ───────────────────────────
def prova_pulizia(hub, s_tel, pagina, svs):
    from calliope.tools import schermi as T
    s_bianca, _ = hub.archivio.crea_con_token("camera", proprietario="bianca",
                                              proprietario_nome="Bianca")
    hub._rinfresca()
    hub.invia(schede.testo("Di Bianca", "x", schede.PERSONALE), BIANCA)
    pb = Conn(hub, s_bianca)
    pagina.eventi()
    prof = {"Dario": SimpleNamespace(id="dario", name="Dario")}

    def ctx(grigia=False, nome="Dario"):
        return SimpleNamespace(schermi=hub, speakers=prof, speaker_ctx=SimpleNamespace(
            current_speaker=nome, current_level="amministra", from_session=grigia))
    r = T._schede_pulisci(ctx(grigia=True))
    verifica("schede_pulisci dalla zona grigia: rifiutato, niente tolto",
             r["ok"] is False and len(hub.cronologia.ultime("dario")) > 0, r.get("conferma"))
    r = T._schede_pulisci(SimpleNamespace(schermi=hub, speakers={}, speaker_ctx=SimpleNamespace(
        current_speaker=None, current_level="ospite", from_session=False)))
    verifica("schede_pulisci da un ospite: rifiutato", r["ok"] is False)
    r = T._schede_pulisci(ctx())
    ev = [e[0] for e in pagina.eventi()]
    verifica("schede_pulisci: tolte le sue, le pagine ricevono «pulisci»",
             r["ok"] and "pulisci" in ev and "scheda" in ev, ev)
    rimaste = [x["scheda"]["tipo"] for x in hub.cronologia.ultime("dario")]
    verifica("lo sviluppo aperto resta (è uno stato), il resto no", rimaste == ["sviluppo"],
             rimaste)
    verifica("le schede di Bianca restano, e la sua pagina non riceve niente",
             len(hub.cronologia.ultime("bianca")) == 1 and not pb.eventi())
    svs.sviluppi[0].stato = "chiusa"
    hub.pulisci_schede("dario")
    p = hub.cronologia.cartella / nome_file("dario")
    verifica("senza schede il file della persona sparisce", not p.exists())
    verifica("frase pronta del tool", "restano dove sono" in T._schede_pulisci(ctx())["conferma"]
             or "Non c'erano" in T._schede_pulisci(ctx())["conferma"])
    from calliope.tools.schermi import schermi_specs
    spec = next(s for s in schermi_specs() if s.name == "schede_pulisci")
    verifica("schede_pulisci: famiglia, azione, classe dichiarata",
             spec.levels == frozenset({"familiare", "amministra"}) and spec.risk == "azione"
             and spec.classe is not None)


# ─────────────────────────── 4. conversazione ───────────────────────────
def turno(domanda, risposta, meta=None, tool=None):
    m = [{"role": "user", "content": domanda, **({"_turno": meta} if meta else {})}]
    if tool:
        m.append({"role": "tool", "name": tool, "content": json.dumps({"ok": True})})
    m.append({"role": "assistant", "content": risposta})
    return m


def prova_conversazione():
    from calliope import conversazioni as CV
    from calliope.conversazione import Conversazione, RISERVATA, SFIDA_DETTA, turni
    from calliope.persistenza import versione_schema
    # Migrazione: un archivio della versione 1 prende la colonna `meta`
    db = TMP / "conv-v1.db"
    con = sqlite3.connect(db)
    CV._v1(con)
    con.execute("CREATE TABLE meta_schema (modulo TEXT PRIMARY KEY, versione INTEGER NOT NULL)")
    con.execute("INSERT INTO meta_schema VALUES ('conversazioni', 1)")
    con.commit()
    con.close()
    a1 = CV.ArchivioConversazioni(db, giorni=30, avvia=False, log=lambda m: None)
    cols = {r[1] for r in a1.db.execute("PRAGMA table_info(turni)")}
    verifica("migrazione: la versione 1 prende `meta` (versione 2)", "meta" in cols
             and versione_schema(a1.db, "conversazioni") == 2 and a1.scrivibile)
    a1.close()

    arch = CV.ArchivioConversazioni(TMP / "conv.db", giorni=30, avvia=False, log=lambda m: None)
    arrivati = []
    arch.su_turni.append(lambda p, v: arrivati.append((p, v)))
    dimenticati = []
    arch.su_dimentica.append(dimenticati.append)
    t0 = time.time() - 60
    c = Conversazione("persona:dario")
    c.luogo = "studio"
    msg = (turno("Che tempo fa domani?", "Domani sole.",
                 {"t": t0, "luogo": "Studio", "canale": "voce"})
           + turno("Mandami l'IBAN IT60X0542811101000000123456 e la mail a@b.it",
                   "Fatto: IT60X0542811101000000123456.", {"t": t0 + 5, "luogo": "Telefono",
                                                           "canale": "scritto"})
           + turno("Spegni lo schermo dello studio", "Per conferma ripeti: girasole, treno, "
                   "quarantadue.", {"t": t0 + 10, "luogo": "Studio", "sfida_chiesta": True})
           + turno("girasole treno quarantadue", "Fatto.",
                   {"t": t0 + 15, "luogo": "Studio", "sfida": True})
           + turno("Abbina lo schermo 123 456", "Abbinato.", {"t": t0 + 20})
           + turno("Cosa c'è nel contratto?", "Il canone è di 900 euro.", {"t": t0 + 25},
                   tool="archivio_cerca"))
    tt = turni(msg, frozenset({"archivio_cerca"}),
               redact=lambda x: x.replace("123 456", "******") if isinstance(x, str) else x)
    arch.archivia(c, tt, "dario", "Dario", ospite=False)
    ch = arch.chat("dario")
    verifica("turni nell'archivio con l'ora, il satellite e il canale",
             [(x["luogo"], x["canale"]) for x in ch[:2]] == [("Studio", "voce"),
                                                            ("Telefono", "scritto")]
             and abs(ch[0]["quando"] - t0) < 1, ch[:2])
    testo = json.dumps(ch, ensure_ascii=False)
    verifica("codici tolti (IBAN, email)", "IT60X" not in testo and "a@b.it" not in testo)
    verifica("frase di sfida: chiesta senza le parole, ripetuta come «frase di conferma»",
             ch[2]["risposta"] == "Per conferma ripeti: …." and ch[3]["domanda"] == SFIDA_DETTA
             and "girasole" not in testo, (ch[2]["risposta"], ch[3]["domanda"]))
    verifica("segreti del turno tolti (codice di abbinamento)",
             "123 456" not in testo and "******" in ch[4]["domanda"], ch[4]["domanda"])
    verifica("risposta riservata non archiviata", ch[5]["risposta"] == RISERVATA)
    verifica("in diretta: i turni appena archiviati, con l'id dell'archivio",
             arrivati and arrivati[0][0] == "dario"
             and [v["id"] for v in arrivati[0][1]] == [x["id"] for x in ch])
    # Ospiti e altre persone
    arrivati.clear()
    g = Conversazione("ospite:locale")
    arch.archivia(g, turni(turno("Ciao", "Ciao!")), None, None, ospite=True)
    b = Conversazione("persona:bianca")
    arch.archivia(b, turni(turno("Mia domanda", "Mia risposta")), "bianca", "Bianca",
                  ospite=False)
    verifica("i turni di un ospite non vanno a nessuno schermo",
             [p for p, _ in arrivati] == ["bianca"])
    verifica("la conversazione di Dario non ha i turni di Bianca né degli ospiti",
             not any("Mia domanda" in x["domanda"] or x["domanda"] == "Ciao"
                     for x in arch.chat("dario")))
    # Tenuta
    vecchio = Conversazione("persona:dario")
    arch.archivia(vecchio, turni(turno("vecchissima", "sì", {"t": time.time() - 40 * 86400})),
                  "dario", "Dario", ospite=False)
    verifica("tenuta come l'archivio: i turni più vecchi non tornano",
             not any(x["domanda"] == "vecchissima" for x in arch.chat("dario")))
    md = arch.chat_markdown("dario")
    verifica("«Scarica» in Markdown: titolo, giorno, ora e luogo, Tu e Calliope",
             md.startswith("# Conversazione con Calliope") and "**Tu:** Che tempo fa domani?"
             in md and "**Calliope:** Domani sole." in md and "Telefono · scritto" in md, md[:300])
    # Il ciclo: _archivia_turno annota il messaggio e archivia
    from calliope.ciclo import Ciclo
    chiamate = []
    hist = [{"role": "user", "content": "a", "_turno": {"t": 1}},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"}, {"role": "assistant", "content": "d"}]
    finto = SimpleNamespace(_meta_turno={"t": 5, "luogo": "Cucina", "canale": "voce"},
                            brain=SimpleNamespace(history=hist,
                                                  archivia_turni=lambda: chiamate.append(1)))
    Ciclo._archivia_turno(finto)
    verifica("ciclo: a turno finito il messaggio prende dove e come, e si archivia subito",
             hist[2].get("_turno", {}).get("luogo") == "Cucina" and hist[0]["_turno"] == {"t": 1}
             and chiamate == [1] and finto._meta_turno is None)
    return arch


def prova_server(arch):
    """Server vero: benvenuto con la cronologia e la conversazione, eventi «chat», «Scarica»,
    POST /api/schede, «dimentica»."""
    from calliope.schermi.server import ServerSchermi
    from calliope.conversazione import Conversazione, turni
    cart = TMP / "schede-server"
    hub = hub_nuovo(cart, db="server.db")
    hub.chat_fonte = arch
    arch.su_turni.append(hub.chat_nuovi)
    arch.su_dimentica.append(hub.chat_dimenticata)
    srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
    hub.server = srv
    base = f"http://127.0.0.1:{srv.port}"
    c = httpx.Client(base_url=base, timeout=5)
    _, tok_d = hub.archivio.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario")
    _, tok_b = hub.archivio.crea_con_token("camera", proprietario="bianca",
                                           proprietario_nome="Bianca")
    _, tok_s = hub.archivio.crea_con_token("cucina")
    hub._rinfresca()
    hub.invia(schede.documento_markdown("Relazione", "# R\n\nok", chiave="lavoro:L9"), DARIO)

    def accedi(t):
        return c.post("/api/accedi", headers={"Authorization": f"Bearer {t}"}).json()["sessione"]
    lettori = {}
    for nome, t in (("dario", tok_d), ("bianca", tok_b), ("cucina", tok_s)):
        lettori[nome] = (Lettore(base, accedi(t)), accedi(t))
    for x, _ in lettori.values():
        x.attendi("benvenuto")
    bd = lettori["dario"][0].di("benvenuto")[0]
    verifica("benvenuto dello schermo personale: le schede della persona e la conversazione",
             [k.get("chiave") for k in bd["cronologia"]] == ["lavoro:L9"]
             and bd["chat"] and len(bd["chat"]["turni"]) >= 6 and bd["cronologia_max"] == 6,
             (bd.get("cronologia"), (bd.get("chat") or {}).get("max")))
    bc = lettori["cucina"][0].di("benvenuto")[0]
    verifica("schermo di stanza: niente conversazione né schede delle persone",
             bc["chat"] is None and bc["cronologia"] == [])
    bb = lettori["bianca"][0].di("benvenuto")[0]
    verifica("schermo di Bianca: solo la sua conversazione",
             [x["domanda"] for x in bb["chat"]["turni"]] == ["Mia domanda"])
    # Un turno nuovo di Dario: in diretta solo ai suoi schermi
    conv = Conversazione("persona:dario")
    arch.archivia(conv, turni(turno("E dopodomani?", "Pioggia.", {"t": time.time(),
                                                                 "luogo": "Studio"})),
                  "dario", "Dario", ospite=False)
    ok = lettori["dario"][0].attendi("chat")
    ev = lettori["dario"][0].di("chat")
    verifica("turno nuovo: in diretta allo schermo personale, solo il pezzo nuovo",
             ok and [t["domanda"] for t in ev[0]["turni"]] == ["E dopodomani?"], ev)
    time.sleep(0.2)
    verifica("…e non agli schermi di Bianca né di stanza",
             not lettori["bianca"][0].di("chat") and not lettori["cucina"][0].di("chat"))
    # «Scarica» della trascrizione: solo dagli schermi personali
    h = {"X-Calliope-Sessione": lettori["dario"][1]}
    r = c.post("/api/scarica", headers=h, json={"chiave": "chat", "formato": "md"})
    url = r.json().get("url", "")
    testo = c.get(url).text if url else ""
    verifica("«Scarica» della conversazione in Markdown dallo schermo personale",
             r.status_code == 200 and "E dopodomani?" in testo and "Mia domanda" not in testo,
             r.text[:200])
    r = c.post("/api/scarica", headers={"X-Calliope-Sessione": lettori["cucina"][1]},
               json={"chiave": "chat", "formato": "md"})
    verifica("…mai da uno schermo di stanza", r.status_code == 403, r.status_code)
    # «Dimentica»: la scheda si svuota
    arch.dimentica("dario")
    ok = lettori["dario"][0].attendi("chat", 2)
    verifica("«dimentica le nostre conversazioni»: la conversazione sparisce anche da qui",
             ok and lettori["dario"][0].di("chat")[-1].get("reset") is True
             and arch.chat("dario") == [])
    # POST /api/schede
    r = c.post("/api/schede", headers={"X-Calliope-Sessione": lettori["cucina"][1]},
               json={"azione": "pulisci"})
    verifica("/api/schede da uno schermo di stanza: 403", r.status_code == 403)
    r = c.post("/api/schede", headers={"X-Calliope-Sessione": "falsa"}, json={"azione": "pulisci"})
    verifica("/api/schede senza sessione: 401", r.status_code == 401)
    r = c.post("/api/schede", headers=h, json={"azione": "altro"})
    verifica("/api/schede con un'azione sconosciuta: 400", r.status_code == 400)
    r = c.post("/api/schede", headers=h, json={"azione": "pulisci"})
    ok = lettori["dario"][0].attendi("pulisci")
    verifica("/api/schede dallo schermo personale: pulite, evento «pulisci»",
             r.status_code == 200 and r.json()["tolte"] >= 1 and ok
             and hub.cronologia.ultime("dario") == [], r.text)
    for x, _ in lettori.values():
        x.stop = True
    srv.ferma()
    hub.archivio.close()
    c.close()


class Lettore:
    def __init__(self, base, sessione):
        self.eventi = []
        self.stop = False
        threading.Thread(target=self._run, args=(base, sessione), daemon=True).start()

    def _run(self, base, sessione):
        ev = None
        try:
            with httpx.stream("GET", f"{base}/eventi?sessione={sessione}", timeout=30) as r:
                for line in r.iter_lines():
                    if self.stop:
                        break
                    if line.startswith("event: "):
                        ev = line[7:]
                    elif line.startswith("data: "):
                        self.eventi.append((ev, json.loads(line[6:])))
        except Exception as e:  # noqa: BLE001
            self.eventi.append(("errore", str(e)))

    def attendi(self, tipo, n=1, max_s=4.0):
        t0 = time.monotonic()
        while time.monotonic() - t0 < max_s:
            if len(self.di(tipo)) >= n:
                return True
            time.sleep(0.01)
        return False

    def di(self, tipo):
        return [d for e, d in self.eventi if e == tipo]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        prova_salvataggio()
        hub, s_tel, pagina, svs = prova_ripresa()
        prova_pulizia(hub, s_tel, pagina, svs)
        hub.archivio.close()
        arch = prova_conversazione()
        prova_server(arch)
        arch.close()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
