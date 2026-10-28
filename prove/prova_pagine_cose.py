"""Prova a secco delle pagine Lavori e programmi, Cassetto e Giochi di «Le mie cose» (28/10/2026,
passo 2c di docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md § 4.5, 4.7, 4.10, issue #258 di
#241; area docs/aree/schermi-telefono.md).

1. **Lavori e programmi** (`raccolte.pagina(…, "lavori")`): lo sviluppo aperto e quello sospeso, i
   lavori in corso con la scheda in diretta della cronologia (non quella di un avvio di prima, che
   sarebbe un altro lavoro con lo stesso id), quello fermo a una domanda con la domanda, i
   programmi, i finiti (in memoria con la scheda finale vera, dopo un riavvio dalla cartella dei
   risultati con la chiave della cartella); solo della persona; la nota è la frase di `lavoro_stato`
   (chi amministra sente anche gli altri, gli altri no); la tessera conta anche gli sviluppi.
2. **Cassetto**: i file della persona (chiave `…:pagina`, «Tieni» non ai minori), quelli del figlio
   al tutore (non a chi amministra se il ragazzo ha i suoi tutori, mai a un altro adulto), il
   minore vede solo i suoi; la nota dei 7 giorni; la tessera dice anche i file dei ragazzi.
3. **Giochi**: i giochi di casa col livello del manifesto (quello di chi amministra solo a lui), il
   gioco del formato di prima mai, al minore solo quelli abilitati dal tutore (con la nota); le
   partite aperte della persona (dove, «qui sotto» sullo schermo che chiede, a chi tocca, punti),
   non quelle degli altri; giochi spenti; la tessera conta gli stessi giochi.
4. **Servizi che mancano**: ogni pagina dà una nota, mai un errore.
5. **Il server** vero su 127.0.0.1: le tre pagine da `/api/raccolte`; la sorgente di «Scarica» di un
   documento resta sul server, registrata per lo schermo; il tasto del cassetto dalla scheda della
   pagina va come prima (`/api/cassetto`: il proprio file sì, quello del figlio senza una
   conversazione a voce no); uno schermo il cui proprietario non ha un profilo (un ospite) 403.

Nomi e dati di fantasia, niente rete né modelli.

    python prove/prova_pagine_cose.py
"""

import datetime
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from calliope import minori  # noqa: E402
from calliope.agenti.ciclo import Lavoro  # noqa: E402
from calliope.agenti.servizio import Lavori  # noqa: E402
from calliope.cassetto import Cassetto  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.schermi import ArchivioSchermi, Schermi, raccolte, schede  # noqa: E402
from calliope.schermi.cronologia import CronologiaSchede  # noqa: E402
from calliope.schermi.giochi import Partita, Posto  # noqa: E402
from calliope.schermi.hub import Mittente  # noqa: E402
from calliope.schermi.server import ServerSchermi  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402

import prova_raccolte as pr  # noqa: E402  (chiedi: le richieste al server)

TMP = Path(tempfile.mkdtemp(prefix="calliope-pagine-cose-"))
ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio and not ok else ""),
          flush=True)
    if not ok:
        ERRORI.append(nome)


class Profilo:
    def __init__(self, pid, nome, admin=False, nascita=None, tutori=()):
        self.id, self.name, self.admin, self.nascita = pid, nome, admin, nascita
        self.fascia, self.tutori, self.preferred_tone, self.preferred_voice = None, list(tutori), None, None


DARIO = Profilo("dario", "Dario", admin=True, nascita="1978-02-02")
BIANCA = Profilo("bianca", "Bianca", nascita="1981-06-06")
LIA = Profilo("lia", "Lia", nascita="2016-04-04", tutori=["bianca"])      # 10 anni, tutrice Bianca


class Persone:
    def __init__(self):
        self.users = {p.name: p for p in (DARIO, BIANCA, LIA)}

    def get(self, nome):
        return self.users.get(nome)

    def by_id(self, pid):
        return next((p for p in self.users.values() if p.id == pid), None)


def lavoro(ident, persona, stato, titolo, tipo="ricerca", **altro):
    lv = Lavoro(id=ident, tipo=tipo, compito=titolo, persona=persona.id, persona_nome=persona.name,
                titolo=titolo)
    lv.stato = stato
    for k, v in altro.items():
        setattr(lv, k, v)
    return lv


class Sviluppi:
    """Gli sviluppi della modalità sviluppo, finti: quello aperto e i sospesi per persona."""

    def __init__(self, voci):
        self.voci = voci

    def corrente(self, persona):
        return next((s for s in self.voci if s.persona == persona and s.stato == "aperta"), None)

    def sospesi(self, persona):
        return [s for s in self.voci if s.persona == persona and s.stato == "sospesa"]

    def scheda(self, sv):
        c = schede.documento_markdown(f"Sviluppo: {sv.titolo}", "testo", chiave=f"sviluppo:{sv.id}", stato=sv.stato)
        c["tipo"], c["sezione"], c["sviluppo"] = "sviluppo", schede.sezione_di("sviluppo"), {"id": sv.id, "stato": sv.stato}
        return c


class Esecuzioni:
    def __init__(self, tutte):
        self.tutte = tutte

    def scheda(self, es, sposta=True):
        return schede.esecuzione(es.titolo, "main.py", "Python", es.stato, [], [{"tipo": "out", "testo": "ciao"}],
                                 0, None, inizio=time.time() - 5, trascorso_s=5, max_s=60, ident=es.id, sposta=sposta)


def servizio_lavori(cfg, voci, sviluppi=(), esecuzioni=()):
    """Il servizio dei lavori vero (stato, scheda, in_tappa…) senza agente né rete."""
    svc = object.__new__(Lavori)
    svc.cfg, svc.lavori, svc._lock, svc.female = cfg, list(voci), threading.Lock(), True
    svc.log = lambda m: None
    svc.sviluppi = Sviluppi(list(sviluppi))
    svc.esecuzioni = Esecuzioni(list(esecuzioni))
    return svc


# ─────────────────────────── 1. Lavori e programmi ───────────────────────────
def lavori():
    cfg = Config()
    cfg.agenti_risultati = str(TMP / "risultati")
    # Un lavoro finito prima di un riavvio: solo nella cartella dei risultati, con id «L2» come uno
    # in memoria adesso
    d = TMP / "risultati" / "gechi-del-deserto"
    d.mkdir(parents=True)
    (d / "lavoro.json").write_text(json.dumps({
        "id": "L2", "tipo": "ricerca", "titolo": "gechi del deserto", "stato": "fatto", "persona": "dario",
        "chi": "Dario", "riassunto": "I gechi del deserto cacciano di notte.",
        "fine": (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat(timespec="seconds")}),
        encoding="utf-8")
    ora = time.time()
    corso = lavoro("L1", DARIO, "in_corso", "orari dei treni", creato=ora - 60, passo="legge le pagine")
    seguito = lavoro("L2", DARIO, "in_corso", "relazione sul fiume", creato=ora - 30, passo="scrive")
    attesa = lavoro("L3", DARIO, "in_attesa", "lettera al condominio", creato=ora - 20)
    attesa.domande = [["Che tono vuoi per la lettera?", None]]
    fatto = lavoro("L4", DARIO, "fatto", "ricetta del pane", creato=ora - 900, fine=ora - 800,
                   risultato={"markdown": True, "testo": "# Pane\n\nFarina e acqua.", "riassunto": "Farina e acqua."})
    altrui = lavoro("L5", BIANCA, "in_attesa", "orto sul balcone", creato=ora - 10)
    altrui.domande = [["Quanti vasi hai?", None]]
    altrui_fatto = lavoro("L6", BIANCA, "fatto", "poesia per la nonna", creato=ora - 500, fine=ora - 400,
                          risultato={"riassunto": "Una poesia."})
    svil = [types.SimpleNamespace(id="S1", persona="dario", stato="aperta", titolo="meteo in cucina"),
            types.SimpleNamespace(id="S2", persona="dario", stato="sospesa", titolo="sveglia"),
            types.SimpleNamespace(id="S3", persona="bianca", stato="aperta", titolo="ricettario")]
    esec = [types.SimpleNamespace(id="L4-1", persona="dario", stato="fatto", titolo="ricetta del pane"),
            types.SimpleNamespace(id="L6-1", persona="bianca", stato="in_corso", titolo="poesia")]
    svc = servizio_lavori(cfg, [corso, seguito, attesa, fatto, altrui, altrui_fatto], svil, esec)
    # La cronologia: la scheda in diretta di L2 in questo avvio; quella di L1 è di un avvio di prima
    cron = CronologiaSchede(TMP / "cronologia", scrivi_subito=True, log=lambda m: None)
    vecchia = schede.lavoro_avanzamento("orari dei treni (un altro lavoro)", "ricerca", "in_corso",
                                        {"passo": "di ieri"}, ident="L1")
    cron.aggiungi("dario", vecchia, vecchia)
    cron.avvio = "adesso"
    viva = schede.lavoro_avanzamento("relazione sul fiume", "ricerca", "in_corso",
                                     {"passo": "scrive il secondo paragrafo", "passi": []}, ident="L2")
    cron.aggiungi("dario", viva, viva)
    hub = types.SimpleNamespace(servizi=types.SimpleNamespace(lavori=svc), tool_ctx=None, lavori=svc,
                                cronologia=cron)
    p = raccolte.pagina(hub, DARIO, "lavori")
    sc = p.get("schede") or []
    chiavi = [c.get("chiave") for c in sc]
    verifica("lavori: sviluppi, in corso (più recente prima), programmi, finiti, nell'ordine",
             chiavi == ["sviluppo:S1", "sviluppo:S2", "lavoro:L3", "lavoro:L2", "lavoro:L1", "esecuzione:L4-1",
                        "lavoro:L4", "lavoro:cartella:gechi-del-deserto"], json.dumps(chiavi))
    per = {c.get("chiave"): c for c in sc}
    verifica("lavori: il lavoro seguito sugli schermi con la scheda in diretta della cronologia",
             (per["lavoro:L2"].get("avanzamento") or {}).get("passo") == "scrive il secondo paragrafo",
             json.dumps(per["lavoro:L2"])[:300])
    verifica("lavori: una scheda di un avvio di prima con lo stesso id non vale (la scheda breve, col passo)",
             per["lavoro:L1"].get("titolo") == "orari dei treni" and not per["lavoro:L1"].get("avanzamento")
             and "legge le pagine" in per["lavoro:L1"].get("riassunto", ""), json.dumps(per["lavoro:L1"])[:300])
    verifica("lavori: quello fermo a una domanda porta la domanda",
             per["lavoro:L3"].get("stato") == "in_attesa" and "tono" in per["lavoro:L3"].get("domanda", ""),
             json.dumps(per["lavoro:L3"])[:300])
    verifica("lavori: il finito in memoria con la scheda finale vera (il documento in Markdown, «Scarica» sul server)",
             per["lavoro:L4"].get("tipo") == "documento" and "_scarica" in per["lavoro:L4"], json.dumps(list(per["lavoro:L4"])))
    disco = per["lavoro:cartella:gechi-del-deserto"]
    verifica("lavori: il finito di prima del riavvio dalla cartella, col riassunto salvato",
             disco.get("tipo") == "lavoro" and "notte" in disco.get("riassunto", ""), json.dumps(disco)[:300])
    verifica("lavori: niente di Bianca nella pagina di Dario",
             not any("orto" in str(c.get("titolo")) or "poesia" in str(c.get("titolo")) or c.get("chiave") == "sviluppo:S3"
                     for c in sc))
    verifica("lavori: la nota è la frase della voce; chi amministra sente anche i lavori degli altri",
             "di Bianca" in p.get("nota", "") and "orto sul balcone" in p.get("nota", ""), p.get("nota"))
    pb = raccolte.pagina(hub, BIANCA, "lavori")
    cb = [c.get("chiave") for c in pb.get("schede") or []]
    verifica("lavori: Bianca vede i suoi (sviluppo, domanda, programma, finito), niente di Dario",
             cb == ["sviluppo:S3", "lavoro:L5", "esecuzione:L6-1", "lavoro:L6"], json.dumps(cb))
    verifica("lavori: la nota di chi non amministra non dice i lavori degli altri",
             "orari" not in pb.get("nota", "") and "fiume" not in pb.get("nota", "") and "vasi" in pb.get("nota", ""),
             pb.get("nota"))
    pl = raccolte.pagina(hub, LIA, "lavori")
    verifica("lavori: un minore senza lavori: pagina vuota, la frase della voce",
             pl.get("schede") == [] and pl.get("nota"), json.dumps(pl))
    t = {x["id"]: x for x in raccolte.tessere(hub, DARIO)}
    verifica("lavori: la tessera conta anche gli sviluppi", t["lavori"]["conto"] == 6
             and "2 sviluppi" in t["lavori"]["stato"] and t["lavori"]["pagina"] is True, json.dumps(t["lavori"]))
    cron.close()
    return svc


# ─────────────────────────── 2. Cassetto ───────────────────────────
def cassetto():
    cas = Cassetto(str(TMP / "cassetto.db"), str(TMP / "cassetto"), log=lambda m: None)
    cas.registry = Persone()
    cas.metti("dario", b"scontrino del ferramenta", "scontrino.txt", "testo", fonte="telefono")
    cas.metti("bianca", b"ricetta della torta", "torta.txt", "testo", fonte="telefono")
    cas.metti("lia", b"compito di geografia", "geografia.txt", "testo", fonte="schermo")
    cas.metti("lia", b"disegno del gatto", "gatto.txt", "testo", fonte="telefono")
    hub = types.SimpleNamespace(servizi=None, tool_ctx=None, cassetto=cas)

    def pag(prof):
        p = raccolte.pagina(hub, prof, "cassetto")
        return p, {c["titolo"]: c for c in p.get("schede") or []}

    p, s = pag(BIANCA)
    verifica("cassetto: Bianca vede i suoi file e quelli di Lia (è la sua tutrice)",
             list(s) == ["Il tuo cassetto", "I file di Lia"]
             and [v["nome"] for v in s["Il tuo cassetto"]["voci"]] == ["torta.txt"]
             and sorted(v["nome"] for v in s["I file di Lia"]["voci"]) == ["gatto.txt", "geografia.txt"], json.dumps(list(s)))
    verifica("cassetto: chiavi della pagina, che una scheda mandata dopo un tasto non sostituisce",
             s["Il tuo cassetto"]["chiave"] == "cassetto:bianca:pagina" and s["I file di Lia"]["chiave"] == "cassetto:lia:pagina")
    chiesti = []
    vera = cas.scheda
    cas.scheda = lambda persona, righe=None, **k: (chiesti.append((persona, k.get("tieni"))), vera(persona, righe, **k))[1]
    pag(BIANCA)
    pag(LIA)
    cas.scheda = vera
    verifica("cassetto: «Tieni» per l'adulto e per la tutrice sui file del figlio, non per il minore",
             chiesti == [("bianca", True), ("lia", True), ("lia", False)], str(chiesti))
    verifica("cassetto: la nota dei 7 giorni e del dato", "7 giorni" in p.get("nota", "") and "dato" in p.get("nota", ""),
             p.get("nota"))
    _, s = pag(DARIO)
    verifica("cassetto: chi amministra non vede i file di Lia (ha i suoi tutori), solo i suoi",
             list(s) == ["Il tuo cassetto"] and [v["nome"] for v in s["Il tuo cassetto"]["voci"]] == ["scontrino.txt"],
             json.dumps(list(s)))
    _, s = pag(LIA)
    verifica("cassetto: il minore vede solo i suoi, senza «Tieni»",
             list(s) == ["Il tuo cassetto"] and len(s["Il tuo cassetto"]["voci"]) == 2
             and not any(v["tieni"] for v in s["Il tuo cassetto"]["voci"]), json.dumps(list(s)))
    senza_tutori = Profilo("lia", "Lia", nascita="2016-04-04")
    cas.registry.users["Lia"] = senza_tutori
    _, s = pag(DARIO)
    verifica("cassetto: senza tutori scritti il figlio è di chi amministra (come a voce)", list(s) == ["Il tuo cassetto", "I file di Lia"])
    _, s = pag(BIANCA)
    verifica("cassetto: mai i file di un altro adulto né del figlio di altri", list(s) == ["Il tuo cassetto"], json.dumps(list(s)))
    cas.registry.users["Lia"] = LIA
    t = {x["id"]: x for x in raccolte.tessere(hub, BIANCA)}
    verifica("cassetto: la tessera dice anche i file di Lia, il conto solo i suoi",
             t["cassetto"]["conto"] == 1 and "2 di Lia" in t["cassetto"]["stato"] and t["cassetto"]["pagina"] is True,
             json.dumps(t["cassetto"]))
    vuota = Profilo("ugo", "Ugo", nascita="1990-01-01")
    _, s = pag(vuota)
    verifica("cassetto: vuoto, con la frase del vuoto", s["Il tuo cassetto"]["voci"] == []
             and s["Il tuo cassetto"]["vuoto"] == "Il cassetto è vuoto.")
    return cas


# ─────────────────────────── 3. Giochi ───────────────────────────
MACCHINA = {"fasi": {"turno": {"comandi": []}}}


def manifesto(nome, titolo, livello="familiare", vecchio=False, giocatori=(1, 2)):
    sch = {"giocatori": {"min": giocatori[0], "max": giocatori[1]}}
    if not vecchio:
        sch["macchina"] = MACCHINA
    return {"nome": nome, "titolo": titolo, "descrizione": f"Gioca a {titolo.lower()}", "livello": livello,
            "scheda": sch}


class Archivio:
    def __init__(self, manifesti):
        self.m = {m["nome"]: m for m in manifesti}

    def attive(self):
        return [{"nome": n} for n in sorted(self.m)]

    def manifesto(self, nome):
        return self.m[nome]


def giochi():
    arch = Archivio([manifesto("tris", "Tris"), manifesto("dama", "Dama"),
                     manifesto("cassaforte", "La cassaforte", livello="amministra"),
                     manifesto("vecchio", "Gioco vecchio", vecchio=True)])
    p = Partita("tris", 1, manifesto("tris", "Tris"), Mittente(persona="dario", nome="Dario", livello="amministra", certo=True))
    p.posti[7] = Posto(7, Mittente(persona="dario", nome="Dario", livello="familiare", certo=True), False)
    p.posti[9] = Posto(9, Mittente(persona="lia", nome="Lia", livello="familiare", certo=True), True)
    p.posti[7].istantanea = {"n": 3, "fase": "turno", "tocca": 1, "turno": 2, "esito": None, "comandi": [],
                             "giocatori": [{"nome": "Dario", "punti": 2}, {"nome": "Lia", "punti": 3}]}
    altra = Partita("dama", 1, manifesto("dama", "Dama"), Mittente(persona="bianca", nome="Bianca", livello="familiare"))
    altra.posti[11] = Posto(11, Mittente(persona="bianca", nome="Bianca", livello="familiare", certo=True), False)
    nomi = {7: "telefono di Dario", 9: "salotto", 11: "cucina"}
    hub = types.SimpleNamespace(servizi=types.SimpleNamespace(estensioni=types.SimpleNamespace(archivio=arch)),
                                tool_ctx=None, cfg=Config(),
                                giochi=types.SimpleNamespace(partite={p.id: p, altra.id: altra}),
                                schermo=lambda sid: {"id": sid, "nome": nomi.get(sid)})

    def pag(prof, schermo=None):
        q = raccolte.pagina(hub, prof, "giochi", schermo)
        return q, {c["chiave"]: c for c in q.get("schede") or []}

    q, s = pag(DARIO, {"id": 7})
    casa = s.get("giochi:casa:dario") or {}
    verifica("giochi: chi amministra vede anche il suo gioco «solo chi amministra», mai quello del formato di prima",
             [g["titolo"] for g in casa.get("giochi") or []] == ["Dama", "La cassaforte", "Tris"], json.dumps(casa)[:300])
    verifica("giochi: come si apre a voce e quanti giocatori",
             (casa.get("giochi") or [{}])[0].get("dire") == "«Calliope, giochiamo a Dama»"
             and casa["giochi"][0].get("giocatori") == "da 1 a 2 giocatori"
             and casa.get("tipo") == "giochi" and casa.get("sezione") == "cose/giochi")
    part = (s.get("giochi:partite:dario") or {}).get("partite") or []
    verifica("giochi: la partita aperta di Dario, qui sotto su questo schermo, a chi tocca e i punti",
             len(part) == 1 and part[0]["titolo"] == "Tris" and part[0]["qui"] is True
             and part[0]["dove"] == ["telefono di Dario", "salotto"] and part[0]["tocca"] == "Lia"
             and part[0]["punti"] == [{"nome": "Dario", "punti": 2}, {"nome": "Lia", "punti": 3}], json.dumps(part))
    verifica("giochi: le partite prima dei giochi di casa", list(s) == ["giochi:partite:dario", "giochi:casa:dario"])
    _, s = pag(DARIO, {"id": 99})
    verifica("giochi: da un altro schermo la partita non è «qui»",
             s["giochi:partite:dario"]["partite"][0]["qui"] is False)
    _, s = pag(BIANCA)
    verifica("giochi: Bianca non vede il gioco di chi amministra; la sua partita, non quella di Dario",
             [g["titolo"] for g in s["giochi:casa:bianca"]["giochi"]] == ["Dama", "Tris"]
             and [x["titolo"] for x in s["giochi:partite:bianca"]["partite"]] == ["Dama"], json.dumps(list(s)))
    # Il minore: solo i giochi abilitati da un tutore (minori.estensione_consentita)
    prima = minori._SERVIZIO.get("regole")
    reg = minori.Regole(str(TMP / "minori.db"))
    minori._SERVIZIO["regole"] = reg
    try:
        reg.imposta("lia", "estensioni", ["tris"])
        q, s = pag(LIA)
        verifica("giochi: al minore solo i giochi che il tutore ha abilitato, con la nota",
                 [g["titolo"] for g in s["giochi:casa:lia"]["giochi"]] == ["Tris"]
                 and "sblocca" in s["giochi:casa:lia"].get("nota", "")
                 and [x["titolo"] for x in s["giochi:partite:lia"]["partite"]] == ["Tris"], json.dumps(s)[:400])
        t = {x["id"]: x for x in raccolte.tessere(hub, LIA)}
        verifica("giochi: la tessera conta gli stessi giochi della pagina",
                 t["giochi"]["conto"] == 1 and "1 partita aperta" in t["giochi"]["stato"] and t["giochi"]["pagina"] is True,
                 json.dumps(t["giochi"]))
    finally:
        minori._SERVIZIO["regole"] = prima
    hub.cfg.giochi_enabled = False
    q = raccolte.pagina(hub, DARIO, "giochi")
    verifica("giochi: spenti, la pagina lo dice", q.get("schede") == [] and "spenti" in q.get("nota", ""), json.dumps(q))


# ─────────────────────────── 4. servizi che mancano ───────────────────────────
def mancano():
    hub = types.SimpleNamespace(servizi=None, tool_ctx=None)
    for k, parola in (("lavori", "agente"), ("cassetto", "cassetto"), ("giochi", "estensioni")):
        q = raccolte.pagina(hub, BIANCA, k)
        verifica(f"servizio che manca: la pagina {k} dice una nota, nessun errore",
                 q.get("schede") == [] and parola in q.get("nota", "").lower() and "_stato" not in q, json.dumps(q))
    t = {x["id"]: x for x in raccolte.tessere(hub, BIANCA, lambda m: None)}
    verifica("servizio che manca: tessere «non disponibile» ma con la pagina",
             all(t[k]["stato"] == "non disponibile" and t[k]["pagina"] for k in ("lavori", "cassetto", "giochi")))
    giusto = types.SimpleNamespace(servizi=None, tool_ctx=None, cassetto=types.SimpleNamespace(
        elenco=lambda p: (_ for _ in ()).throw(RuntimeError("database chiuso"))))
    log = []
    t = {x["id"]: x for x in raccolte.tessere(giusto, BIANCA, log.append)}
    verifica("servizio che solleva: la tessera «non disponibile», detto nel registro",
             t["cassetto"]["stato"] == "non disponibile" and any("cassetto" in m for m in log))


# ─────────────────────────── 5. il server ───────────────────────────
def server(svc, cas):
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "memoria.db")
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    reg = Persone()
    hub.profilo = reg.by_id
    hub.cassetto = cas
    hub.lavori = svc
    hub.tool_ctx = ToolContext(cfg=cfg, speakers=reg, speaker_ctx=None, speaker=None, lavori=svc)
    srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
    hub.server = srv
    try:
        sid_d, t_dario = hub.archivio.crea_con_token("telefono", proprietario="dario", proprietario_nome="Dario")
        _, t_bianca = hub.archivio.crea_con_token("telefono", proprietario="bianca", proprietario_nome="Bianca")
        _, t_ugo = hub.archivio.crea_con_token("telefono", proprietario="ugo", proprietario_nome="Ugo")
        hub._rinfresca()
        port = srv.port
        sess_d = pr.chiedi(port, "/api/accedi", token=t_dario)[1].get("sessione")
        sess_b = pr.chiedi(port, "/api/accedi", token=t_bianca)[1].get("sessione")
        sess_u = pr.chiedi(port, "/api/accedi", token=t_ugo)[1].get("sessione")
        sid_d = next(s["id"] for s in hub.abbinati() if s.get("proprietario") == "dario")
        st, d = pr.chiedi(port, "/api/raccolte", sess_d, corpo={"raccolta": "lavori"})
        sc = {c.get("chiave"): c for c in d.get("schede") or []}
        verifica("server: la pagina Lavori dal servizio", st == 200 and "lavoro:L4" in sc and "sviluppo:S1" in sc,
                 f"{st} {json.dumps(d)[:300]}")
        verifica("server: nessuna chiave privata va alla pagina",
                 not any(str(k).startswith("_") for c in d.get("schede") or [] for k in c), json.dumps(list(sc.get("lavoro:L4", {}))))
        verifica("server: «Scarica» del documento registrato per lo schermo che ha chiesto la pagina",
                 (sid_d, "lavoro:L4") in hub.scaricamenti._voci)
        st, d = pr.chiedi(port, "/api/raccolte", sess_b, corpo={"raccolta": "cassetto"})
        sc = {c.get("titolo"): c for c in d.get("schede") or []}
        verifica("server: la pagina Cassetto di Bianca, con i file di Lia",
                 st == 200 and list(sc) == ["Il tuo cassetto", "I file di Lia"] and "7 giorni" in d.get("nota", ""),
                 f"{st} {json.dumps(d)[:300]}")
        suo = sc["Il tuo cassetto"]["voci"][0]["id"]
        st, d = pr.chiedi(port, "/api/cassetto", sess_b, corpo={"azione": "ancora", "id": [suo]})
        verifica("server: il tasto della scheda della pagina va come prima (il proprio file)",
                 st == 200 and d.get("ok") is True, f"{st} {d}")
        di_lia = sc["I file di Lia"]["voci"][0]["id"]
        st, d = pr.chiedi(port, "/api/cassetto", sess_b, corpo={"azione": "elimina", "id": [di_lia]})
        verifica("server: sul file del figlio senza una conversazione a voce no, come prima",
                 st == 403 and d.get("codice") == "senza_conversazione" and cas.proprietario(di_lia) == "lia", f"{st} {d}")
        st, d = pr.chiedi(port, "/api/raccolte", sess_d, corpo={"raccolta": "cassetto"})
        verifica("server: Dario non vede il cassetto di Lia", st == 200
                 and [c.get("titolo") for c in d.get("schede") or []] == ["Il tuo cassetto"], f"{st} {json.dumps(d)[:200]}")
        st, d = pr.chiedi(port, "/api/raccolte", sess_b, corpo={"raccolta": "giochi"})
        verifica("server: la pagina Giochi senza estensioni lo dice", st == 200 and d.get("schede") == []
                 and "estensioni" in d.get("nota", ""), f"{st} {d}")
        st, d = pr.chiedi(port, "/api/raccolte", sess_u, corpo={"raccolta": "lavori"})
        verifica("server: uno schermo il cui proprietario non ha un profilo (ospite) 403", st == 403, f"{st} {d}")
    finally:
        srv.ferma()


def main():
    try:
        print("— 1. Lavori e programmi")
        svc = lavori()
        print("— 2. Cassetto")
        cas = cassetto()
        print("— 3. Giochi")
        giochi()
        print("— 4. servizi che mancano")
        mancano()
        print("— 5. il server")
        server(svc, cas)
        cas.close()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(ERRORI)} errori" if ERRORI else "\ntutto ok")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
