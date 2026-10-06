import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Il cruscotto di chi amministra (06/10/2026, calliope/schermi/cruscotto.py), a secco: server
degli schermi vero su 127.0.0.1, registro dei turni finto, nessun modello.

- chi lo vede: lo schermo personale di chi amministra sì; quello di un familiare, quello di
  stanza, quello di una persona che non c'è più (ospite) no; senza sessione 401; un
  amministratore tolto non lo vede alla richiesta dopo; speakers.json illeggibile: nessuno;
  `/api/accedi` dice «amministra» solo a chi può;
- cosa c'è: versione, capacità con motivo e passo, latenza per giorno con base, avviso, guasti
  del guardiano e attesa delle schede, satelliti e schermi (collegati, inattivi da 7 giorni),
  regole per nome e per profilo, errori (solo il tipo), richieste in attesa (tutori, estensioni,
  lavori);
- niente testi di persone nella risposta: frasi, risposte, messaggi d'errore, titoli dei lavori
  con un segno riconoscibile non escono mai;
- il prefisso del modello non cambia: nessun tool, niente nel prompt (stessa costruzione di
  prova_brain, con e senza il cruscotto acceso);
- costo: registro grande (7 giorni × 4000 turni), primo calcolo, cache, solo il file di oggi
  riletto quando cresce.
"""

import datetime
import json
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from calliope.config import Config
from calliope.schermi import ArchivioSchermi, Schermi
from calliope.schermi.cruscotto import Cruscotto, tipo_errore
from calliope.schermi.server import ServerSchermi

TMP = Path(tempfile.mkdtemp(prefix="calliope-cruscotto-"))
ERRORI = []
SEGNO = "ZQXSEGRETOZQX"          # nei testi di persone: non deve mai uscire


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


class Profilo:
    def __init__(self, pid, nome, admin=False):
        self.id, self.name, self.admin = pid, nome, admin


class Registro:
    illeggibile = False

    def __init__(self, *profili):
        self.p = {x.id: x for x in profili}

    def by_id(self, pid):
        return self.p.get(pid)


class Lavoro:
    def __init__(self, stato, titolo):
        self.stato, self.titolo, self.persona = stato, titolo, "dario"


class Lavori:
    def __init__(self):
        self.lavori = [Lavoro("in_attesa", f"relazione {SEGNO}"), Lavoro("in_corso", SEGNO)]

    def in_attesa(self, persona=None):
        return [x for x in self.lavori if x.stato == "in_attesa"]

    def attivi(self, persona=None, attesa=False):
        return [x for x in self.lavori if x.stato in ("in_coda", "in_corso")]


class Servizi:
    def __init__(self, registry):
        self.registry = registry
        self.lavori = Lavori()
        self.satelliti = None


def turno(giorno, i, **kw):
    t = {"inizio": f"{giorno}T10:{i // 60 % 60:02d}:{i % 60:02d}.000", "livello": "familiare",
         "testo": f"Calliope, {SEGNO} che ore sono", "richiesta": f"{SEGNO} richiesta",
         "risposta": f"Sono le dieci {SEGNO}", "prima_frase_s": 0.9 + (i % 10) / 10,
         "stt_s": 0.2, "regole": ["cortesia"] if i % 3 == 0 else [], "profilo": "gemma4-e4b-ollama",
         "modello": "gemma4:e4b-it-qat"}
    t.update(kw)
    return t


def registro_turni(cartella: Path, giorni: int, per_giorno: int) -> list[str]:
    cartella.mkdir(parents=True, exist_ok=True)
    oggi = datetime.date.today()
    date = []
    for g in range(giorni):
        d = (oggi - datetime.timedelta(days=giorni - 1 - g)).isoformat()
        date.append(d)
        with open(cartella / f"turni-{d}.jsonl", "w", encoding="utf-8") as f:
            for i in range(per_giorno):
                kw = {}
                if i % 50 == 0:
                    kw["guardiano"] = {"frasi": 1, "ms": [80], "schede_attesa_ms": 150.0 + i % 7,
                                       **({"guasto": True} if i % 100 == 0 else {})}
                if i % 97 == 0:
                    kw["errore"] = f"ValueError: {SEGNO} nella frase"
                if i % 211 == 0:
                    kw["errore"] = f"{SEGNO} senza tipo"
                if i % 7 == 0:
                    kw["regole"] = ["textcallguard"]
                    kw["profilo"] = "gemma4-26b-ollama"
                f.write(json.dumps(turno(d, i, **kw), ensure_ascii=False) + "\n")
            f.write("{riga rotta\n")
    return date


def chiedi(port, percorso, sessione=None, token=None, metodo="GET"):
    h = {}
    if sessione:
        h["X-Calliope-Sessione"] = sessione
    if token:
        h["Authorization"] = "Bearer " + token
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:{port}{percorso}", headers=h, method=metodo,
                                 data=b"{}" if metodo == "POST" else None)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def prova_server():
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "memoria.db")
    cfg.turn_log_dir = str(TMP / "registro")
    cfg.estensioni_cartella = str(TMP / "estensioni")
    registro_turni(TMP / "registro", 3, 300)
    # Un'estensione da approvare e un avviso ai tutori non ancora detto
    (TMP / "estensioni").mkdir()
    (TMP / "estensioni" / "indice.json").write_text(json.dumps({
        "meteo": {"stato": "da_approvare", "versioni": {"1": {"stato": "da_approvare",
                                                              "test_passano": True,
                                                              "chi": SEGNO}}},
        "vecchia": {"stato": "attiva", "versioni": {"1": {"stato": "approvata"}}}}),
        encoding="utf-8")
    from calliope.minori import Avvisi
    av = Avvisi(cfg.memory_db, log=lambda m: None)
    av.db.execute("INSERT INTO avvisi_tutori (tutore, minore, tipo, testo, urgente, creato) "
                  "VALUES ('dario', 'bianca', 'pericolo', ?, 1, '2026-10-06T10:00:00')",
                  (f"ha parlato di {SEGNO}",))
    av.db.commit()
    av.close()

    reg = Registro(Profilo("dario", "Dario", admin=True), Profilo("bianca", "Bianca"))
    servizi = Servizi(reg)
    from calliope import capacita
    capreg = capacita.Registro()
    capreg.segnala("llm", "attiva", "gemma4")
    capreg.segnala("casa", "guasta", "Home Assistant non risponde", "Controlla il Raspberry.",
                   {"token": SEGNO})
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
    hub.server = srv
    hub.cruscotto = Cruscotto(cfg, hub, servizi=servizi, registro_capacita=capreg)
    try:
        arch = hub.archivio
        _, t_admin = arch.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario")
        _, t_fam = arch.crea_con_token("camera", proprietario="bianca", proprietario_nome="Bianca")
        _, t_stanza = arch.crea_con_token("cucina")
        _, t_via = arch.crea_con_token("sala", proprietario="ugo", proprietario_nome="Ugo")
        vecchio, _ = arch.crea_con_token("taverna")
        arch.db.execute("UPDATE schermi SET creato = ?, visto = ? WHERE id = ?",
                        (time.time() - 10 * 86400, time.time() - 9 * 86400, vecchio["id"]))
        arch.db.commit()
        arch.versione += 1
        hub._rinfresca()
        port = srv.port

        def accedi(tok):
            st, d = chiedi(port, "/api/accedi", token=tok, metodo="POST")
            return d
        a = accedi(t_admin)
        verifica("accedi: lo schermo personale di chi amministra ha «amministra»",
                 a.get("amministra") is True, a.get("amministra"))
        for nome, tok in (("familiare", t_fam), ("di stanza", t_stanza), ("di chi non c'è", t_via)):
            d = accedi(tok)
            verifica(f"accedi: schermo {nome} senza «amministra»", d.get("amministra") is False,
                     d.get("amministra"))
            st, r = chiedi(port, "/api/cruscotto", d["sessione"])
            verifica(f"cruscotto: schermo {nome} → 403", st == 403, (st, r))
            verifica(f"cruscotto: schermo {nome} → nessun dato", set(r) == {"errore"}, list(r))
        st, r = chiedi(port, "/api/cruscotto")
        verifica("cruscotto senza sessione → 401", st == 401, st)
        st, r = chiedi(port, "/api/cruscotto", "sessione-inventata")
        verifica("cruscotto con una sessione inventata → 401", st == 401, st)

        t0 = time.perf_counter()
        st, d = chiedi(port, "/api/cruscotto", a["sessione"])
        ms = (time.perf_counter() - t0) * 1000
        verifica("cruscotto di chi amministra → 200", st == 200, (st, d.get("errore")))
        testo = json.dumps(d, ensure_ascii=False)
        verifica("nessun testo di persone (frasi, risposte, errori, titoli, dettagli, avvisi)",
                 SEGNO not in testo, testo[max(0, testo.find(SEGNO) - 80):testo.find(SEGNO) + 20]
                 if SEGNO in testo else "")
        verifica("nessun token né hash nella risposta", "token_hash" not in testo
                 and t_admin not in testo and t_fam not in testo)
        print(f"     prima risposta {ms:.0f} ms, calcolo {d.get('calcolo_ms')} ms")

        v = d["versione"]
        # Dal repository (nell'hook la copia dell'indice non è un repository: vuota, non rotta)
        verifica("versione: c'è, dal repository", v.get("origine") == "repository"
                 and set(v) == {"origine", "descrizione", "commit", "installata"}, v)
        from calliope.schermi.cruscotto import versione_in_uso
        (TMP / "versione").mkdir()
        (TMP / "versione" / "VERSIONE.json").write_text(json.dumps(
            {"id": "20261006-abc1234", "commit": "abc1234def5678", "descrizione": "abc1234",
             "installata": "2026-10-06T10:00:00"}), encoding="utf-8")
        v = versione_in_uso(TMP / "versione")
        verifica("versione: da VERSIONE.json del gestore (DGX)",
                 (v["origine"], v["commit"], v["descrizione"]) == ("installata", "abc1234def56",
                                                                   "abc1234"), v)
        cap = d["capacita"]
        casa = next((x for x in cap["voci"] if x["nome"] == "casa"), {})
        verifica("capacità: stato, motivo, prossimo passo (senza i dettagli)",
                 (cap["attive"], cap["totale"], casa.get("stato"), casa.get("prossimo_passo"),
                  "dettagli" in casa) == (1, 2, "guasta", "Controlla il Raspberry.", False), cap)
        lat = d["latenza"]
        oggi = datetime.date.today().isoformat()
        g = lat["giorni"][0]
        verifica("latenza: giorni dal più recente, risposte, mediana, p90, base",
                 (len(lat["giorni"]), g["data"], g["risposte"]) == (3, oggi, 300)
                 and g["prima_frase"]["mediana"] is not None and g["base"]["n"] > 0,
                 (len(lat["giorni"]), g["data"], g["risposte"]))
        verifica("latenza: avviso con la mediana oltre la soglia", bool(g["avviso"]), g["avviso"])
        verifica("latenza: guasti del guardiano e il loro avviso",
                 (g["guardiano"]["guasti"], bool(g["avviso_guasti"])) == (3, True), g["guardiano"])
        verifica("latenza: attesa delle schede trattenute",
                 g["schede_attesa"]["n"] == 6 and g["schede_attesa"]["ms_max"] == 155.0,
                 g["schede_attesa"])
        regole = {x["regola"]: x["n"] for x in d["regole"]["totali"]}
        profili = {x["profilo"]: x for x in d["regole"]["per_profilo"]}
        verifica("regole: conteggi per regola", regole.get("textcallguard") == 3 * 43
                 and regole.get("cortesia") == 3 * (100 - 15), regole)
        verifica("regole: per profilo", set(profili) == {"gemma4-e4b-ollama", "gemma4-26b-ollama"}
                 and profili["gemma4-26b-ollama"]["turni"] == 3 * 43, list(profili))
        er = d["errori"]
        tipi = {x["tipo"]: x["n"] for x in er["per_tipo"]}
        verifica("errori: solo il tipo (ValueError, «errore» senza tipo)",
                 tipi == {"ValueError": 3 * 3, "errore": 3 * 2}, tipi)
        ab = d["abbinamenti"]
        sch = {x["nome"]: x for x in ab["schermi"]}
        verifica("schermi: tutti, personale di chi, collegato o no",
                 len(sch) == 5 and sch[next(n for n in sch if sch[n]["stanza"] == "studio")]
                 ["personale_di"] == "Dario", list(sch))
        inatt = [x["stanza"] for x in ab["schermi"] if x["inattivo"]]
        verifica("schermi: inattivo da più di 7 giorni segnalato (solo quello)",
                 inatt == ["taverna"], inatt)
        verifica("satelliti: senza server letti dal file (nessuno)", ab["satelliti"] == []
                 and ab["server_satelliti"] is False, ab["satelliti"])
        at = d["attesa"]
        verifica("in attesa: avvisi ai tutori (solo quanti)", at["tutori"]["n"] == 1
                 and at["tutori"]["urgenti"] == 1, at["tutori"])
        verifica("in attesa: estensioni da approvare (nome e versione)",
                 at["estensioni"]["da_approvare"] == [{"nome": "meteo", "versione": 1,
                                                       "test_passano": True}],
                 at["estensioni"]["da_approvare"])
        verifica("in attesa: lavori (solo quanti)", (at["lavori"]["in_attesa"],
                                                     at["lavori"]["attivi"]) == (1, 1), at["lavori"])

        # Cache: una seconda richiesta non ricalcola; «aggiorna» sì (oltre i 5 s), e solo il
        # file cambiato si rilegge
        calcoli = hub.cruscotto.calcoli
        chiedi(port, "/api/cruscotto", a["sessione"])
        verifica("cache: la seconda richiesta non ricalcola", hub.cruscotto.calcoli == calcoli)
        chiedi(port, "/api/cruscotto?aggiorna=1", a["sessione"])
        verifica("«aggiorna» entro 5 s: dalla cache", hub.cruscotto.calcoli == calcoli)

        # Amministratore tolto (o registro illeggibile): la richiesta dopo è rifiutata
        reg.p["dario"].admin = False
        st, _ = chiedi(port, "/api/cruscotto", a["sessione"])
        verifica("amministratore tolto → 403 alla richiesta dopo", st == 403, st)
        reg.p["dario"].admin = True
        reg.illeggibile = True
        st, _ = chiedi(port, "/api/cruscotto", a["sessione"])
        verifica("speakers.json illeggibile → 403", st == 403, st)
        reg.illeggibile = False
        hub.cruscotto = None
        st, _ = chiedi(port, "/api/cruscotto", a["sessione"])
        verifica("senza cruscotto → 404", st == 404, st)
    finally:
        srv.ferma()
        hub.archivio.close()


def prova_costo():
    """Registro grande: 7 giorni × 4000 turni (~10 MB). Primo calcolo, poi solo il file di oggi
    riletto quando cresce, gli altri dalla cache."""
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "costo.db")
    cfg.turn_log_dir = str(TMP / "grande")
    date = registro_turni(TMP / "grande", 7, 4000)
    mb = sum(f.stat().st_size for f in (TMP / "grande").glob("*.jsonl")) / 1e6
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    from calliope import capacita
    cr = Cruscotto(cfg, hub, servizi=Servizi(Registro()), registro_capacita=capacita.Registro())
    try:
        t0 = time.perf_counter()
        d = cr.dati()
        primo = time.perf_counter() - t0
        verifica(f"registro grande ({mb:.1f} MB, 28 000 turni): primo calcolo sotto 10 s",
                 primo < 10, f"{primo:.2f} s")
        verifica("registro grande: 7 giorni", len(d["latenza"]["giorni"]) == 7)
        t0 = time.perf_counter()
        cr.dati()
        # Il tempo dipende dal carico (il runner fa girare le prove in parallelo): il controllo
        # vero è quanti file si rileggono, qui sotto
        verifica("dalla cache: sotto 50 ms", time.perf_counter() - t0 < 0.05,
                 f"{(time.perf_counter() - t0) * 1000:.2f} ms")
        with open(TMP / "grande" / f"turni-{date[-1]}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(turno(date[-1], 1)) + "\n")
        letti = []
        import calliope.latenza as lat
        vero = lat.leggi_file
        lat.leggi_file = lambda p: (letti.append(Path(p).name), vero(p))[1]
        try:
            t0 = time.perf_counter()
            cr._quando = 0.0                 # cache scaduta, come dopo 25 s
            d2 = cr.dati()
            dopo = time.perf_counter() - t0
        finally:
            lat.leggi_file = vero
        verifica("un turno in più: si rilegge solo il file di oggi", letti == [f"turni-{date[-1]}.jsonl"],
                 letti)
        verifica("e conta il turno nuovo", d2["latenza"]["giorni"][0]["risposte"] == 4001,
                 d2["latenza"]["giorni"][0]["risposte"])
        print(f"     primo {primo:.2f} s, poi {dopo:.2f} s ({mb:.1f} MB)")
    finally:
        hub.archivio.close()


def prova_tipo_errore():
    casi = {"ConnectionError: [Errno 111] rifiutata": "ConnectionError",
            "httpx.ReadTimeout: timed out": "httpx.ReadTimeout",
            "Server disconnected without sending a response.": "errore",
            "KeyError": "KeyError", "": "errore", "StopIteration": "StopIteration",
            "Dario: dimmi la password": "errore", "Mario Rossi": "errore"}
    for testo, atteso in casi.items():
        verifica(f"tipo dell'errore di «{testo[:30]}»", tipo_errore(testo) == atteso,
                 tipo_errore(testo))


def prova_prefisso():
    """Il cruscotto non tocca il modello: stesso prefisso (system + tool) con gli schermi e il
    cruscotto acceso, nessun tool né parola nuova (la prova di riferimento è
    prova_brain.prova_prefisso_uguale)."""
    from ollama_finto import FakeOllama
    from calliope.brain import Brain
    from calliope.tools.builtin import build_registry
    cfg = Config()
    fake = FakeOllama(modelli=(cfg.llm_model,))
    fake.predefinita = {"content": "Ciao."}
    fake.avvia()
    try:
        cfg.llm_native_url = fake.url
        reg = build_registry(biblioteca=True, schermi=True, agenti=True)
        b = Brain(cfg, reg, None)
        "".join(b.stream_reply("Ciao", "amministra"))
        r = fake.richieste[-1]
        prefisso = json.dumps([r["messages"][0], r.get("tools")], ensure_ascii=False)
        nomi = [t["function"]["name"] for t in r.get("tools") or []]
        verifica("prefisso: nessun tool del cruscotto", not any("crusc" in n for n in nomi), nomi)
        verifica("prefisso: il prompt non parla del cruscotto", "crusc" not in prefisso.lower())
    finally:
        fake.ferma()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        prova_tipo_errore()
        prova_server()
        prova_costo()
        prova_prefisso()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
