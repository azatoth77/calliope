"""Prova a secco del cambio di proprietario dello stesso schermo (31/10/2026, issue #338 di #251;
area docs/aree/schermi-telefono.md).

Lo schermo resta lo stesso (numero e istante dell'abbinamento) quando diventa personale di un'altra
persona: «rendilo personale di Bianca» (`tools/schermi.py`) o il satellite reso personale da
terminale (`ServerSatelliti._allinea_schermo`). Dalla #338 il proprietario fa parte dell'identità
dello schermo che controllano la coda, `invia`/`invia_a`/`evento_a` e `collega`:

1. **Riproduzione** (cadeva prima della correzione): la scheda personale di Dario nella cronologia in
   memoria dello schermo non torna alla pagina di Bianca al collegamento (per tutte e due le
   strade); la risposta scritta, le schede e l'esito di un tocco di Dario ancora in coda non vanno
   allo schermo ora di Bianca, né nella cronologia su disco di Bianca; la pagina aperta del
   proprietario di prima riceve «proprietario» (svuota e rifà l'accesso) e non riceve più niente;
   la corsa fra `abbinati()` e il lock di `invia`, `invia_a` e degli eventi personali
   (`_a_personali`).
2. **I due difetti bassi**: `abbinati()` pubblica l'elenco dopo aver aggiornato le identità (una
   scheda per lo schermo riabbinato in quell'istante non si perde); l'aggiornamento della scheda
   pubblica del tocco porta l'identità dello schermo d'origine (`Mittente.schermo_identita`).
3. **`per_schermo`**: un satellite collegato col numero di uno schermo revocato non risponde a voce
   per lo schermo nuovo che ha preso quel numero.
4. **Contrari**: ricollegamento, token rinnovato, flusso SSE riaperto, stesso proprietario rimesso
   (dal tool, dal satellite, dall'archivio), l'elemento in coda con la sua identità: tutto arriva
   come prima.
5. **Il server vero** su 127.0.0.1: l'elemento in coda porta il proprietario; il flusso SSE aperto
   riceve «proprietario» e si chiude; il benvenuto di Bianca non ha la scheda di Dario.

Nomi e dati di fantasia, niente rete né modelli.

    python prove/prova_schermi_proprietario.py
"""

import http.client
import json
import shutil
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from calliope.config import Config  # noqa: E402
from calliope.schermi import ArchivioSchermi, Mittente, Schermi  # noqa: E402
from calliope.schermi.archivio import di_quale_schermo  # noqa: E402
from calliope.schermi.server import ServerSchermi  # noqa: E402

import prova_raccolte as pr  # noqa: E402  (i finti del 2a: persone, hub, ciclo)

TMP = Path(tempfile.mkdtemp(prefix="calliope-schermi-proprietario-"))
pr.TMP = TMP
ERRORI = []
NOTA = {"tipo": "testo", "chiave": "nota:dario", "visibilita": "personale", "testo": "di Dario"}


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio and not ok else ""),
          flush=True)
    if not ok:
        ERRORI.append(nome)


class CicloFinto:
    """Il ciclo del server per una connessione: ciò che le arriva, senza asyncio."""

    def __init__(self):
        self.arrivati = []

    def call_soon_threadsafe(self, f, item):
        self.arrivati.append(item)

    def tipi(self):
        return [t for t, _ in self.arrivati]

    def con(self, testo):
        return [x for x in self.arrivati if testo in str(x)]


class Cronologia:
    """La cronologia su disco per persona (cronologia.py), solo ciò che le si aggiunge."""

    def __init__(self):
        self.aggiunte = []

    def aggiungi(self, persona, scheda, storia):
        self.aggiunte.append((persona, scheda.get("chiave")))

    def ultime(self, persona):
        return []

    def di(self, persona, chiave):
        return [x for x in self.aggiunte if x == (persona, chiave)]


def hub_nuovo(nome):
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / f"memoria-{nome}.db")
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    hub.profilo = pr.Persone().by_id
    hub.cronologia = Cronologia()
    return hub


def riga(hub, sid):
    return next(s for s in hub.abbinati() if s["id"] == sid)


def tel_di(hub, chi, nome, stanza="telefono", satellite=None):
    r, _ = hub.archivio.crea_con_token(stanza, proprietario=chi, proprietario_nome=nome,
                                       satellite=satellite)
    hub._rinfresca()
    return riga(hub, r["id"])


def personale_di(hub, sid, chi, nome):
    """Come fa «rendilo personale di …» (tools/schermi.py) dopo il «sì»."""
    assert hub.archivio.imposta_proprietario(sid, chi, nome) is not None
    hub._rinfresca()


def con_storia(hub, sid, chiave):
    return [x for x in hub.storia(sid) if x.get("chiave") == chiave]


def ctx_tool(hub, turno):
    reg = pr.Persone()
    sc = types.SimpleNamespace(current_speaker="Dario", current_level="amministra",
                               identified_by="voce", from_session=False)
    return types.SimpleNamespace(cfg=hub.cfg, speakers=reg, speaker_ctx=sc, schermi=hub,
                                 turno=turno, rules=[])


def tool_personale(hub, stanza, persona):
    """«Calliope, rendi il telefono personale di Bianca» e poi «sì»: il tool vero."""
    from calliope.tools import schermi as T
    r1 = T._proprietario(ctx_tool(hub, 1), hub, "personale", stanza, persona)
    r2 = T._proprietario(ctx_tool(hub, 2), hub, "personale", stanza, persona)
    return r1, r2


def satellite_finto(hub, sid, proprietario, nome):
    """`ServerSatelliti` senza rete: solo ciò che usano `_allinea_schermo` e `per_schermo`."""
    from calliope.satellite.server import ServerSatelliti
    srv = ServerSatelliti.__new__(ServerSatelliti)
    srv.schermi, srv.log = hub, (lambda m: None)
    srv._cond = threading.Condition()
    coll = types.SimpleNamespace(satellite={"id": 1, "nome": "studio", "proprietario": proprietario,
                                            "proprietario_nome": nome},
                                 schermo_id=sid, schermo_creato=riga(hub, sid)["creato"], pronto=True,
                                 chiuso=threading.Event(), stanza="studio")
    srv.collegati = [coll]
    return srv, coll


# ─────────────────────────── 1. la riproduzione ───────────────────────────
def collegamento():
    """La scheda personale di Dario in memoria sullo schermo; lo schermo diventa di Bianca; la
    pagina (nuova o ricollegata) non la riceve. Per le due strade."""
    for strada in ("tool", "satellite"):
        hub = hub_nuovo(f"collega-{strada}")
        # Lo schermo del satellite numero 1 (colonna `satellite`, come lo abbina ServerSatelliti._schermo)
        tel = tel_di(hub, "dario", "Dario", stanza=f"studio{strada}", satellite=1)
        sid = tel["id"]
        hub.invia_a(sid, dict(NOTA))
        verifica(f"{strada}: la scheda personale di Dario è nella cronologia del suo schermo",
                 bool(con_storia(hub, sid, "nota:dario")))
        if strada == "tool":
            r1, r2 = tool_personale(hub, f"studio{strada}", "Bianca")
            verifica("tool: «rendilo personale di Bianca», proposta e poi «sì»",
                     "proposta" in str(r1.get("fatto")) and r2.get("fatto") == "personale",
                     f"{r1} {r2}")
        else:
            srv, coll = satellite_finto(hub, sid, "bianca", "Bianca")
            srv._allinea_schermo(coll)
        nuova = riga(hub, sid)
        loop = CicloFinto()
        conn, storia = hub.collega(nuova, loop)
        verifica(f"{strada}: lo schermo è di Bianca, stesso numero e stesso abbinamento",
                 nuova["proprietario"] == "bianca" and nuova["creato"] == tel["creato"])
        verifica(f"{strada}: al collegamento la pagina di Bianca non riceve la scheda personale di Dario",
                 not [x for x in storia if x.get("chiave") == "nota:dario"]
                 and not con_storia(hub, sid, "nota:dario"),
                 str([x.get("chiave") for x in storia]))
        hub.scollega(conn)


def coda():
    """Una frase scritta e un tocco di Dario ancora in coda quando lo schermo diventa di Bianca."""
    from calliope.rispondi import Instradamento
    hub = hub_nuovo("coda")
    tel = tel_di(hub, "dario", "Dario")
    sid = tel["id"]
    item = {"tipo": "scritto", "testo": "che ho in agenda?", "persona": "dario",
            "schermo_id": sid, "schermo_creato": tel["creato"], "schermo_proprietario": "dario"}
    personale_di(hub, sid, "bianca", "Bianca")
    loop = CicloFinto()
    conn, _ = hub.collega(riga(hub, sid), loop)
    ist = Instradamento.__new__(Instradamento)
    ist.schermi = hub
    ok = ist.risposta_scritta(item, "che ho in agenda?", "Dentista alle cinque.")
    verifica("coda: la risposta scritta di Dario non va allo schermo diventato di Bianca",
             ok is False and not loop.con("Dentista") and not hub.storia(sid),
             f"{ok} {loop.arrivati}")
    verifica("coda: né nella cronologia su disco di Bianca",
             not [x for x in hub.cronologia.aggiunte if x[0] == "bianca"], str(hub.cronologia.aggiunte))
    verifica("coda: evento_a e invia_a con il proprietario di prima non arrivano",
             hub.evento_a(sid, "tocco", {}, **di_quale_schermo(item)) == 0
             and hub.invia_a(sid, dict(NOTA), **di_quale_schermo(item)) is False)
    # Contrario: con l'identità di adesso arriva
    item_b = dict(item, persona="bianca", schermo_proprietario="bianca")
    verifica("contrario: la risposta scritta dello schermo con il proprietario di adesso arriva",
             ist.risposta_scritta(item_b, "che ore sono?", "Le dieci.") is True and loop.con("Le dieci"))
    hub.scollega(conn)

    # Il tocco, col ciclo vero: la lista e l'esito
    b, c, sc, liste, turni, voce, finto, _ = pr.prepara_ciclo()
    pr.CORRENTE["liste"] = liste
    try:
        hub2 = hub_nuovo("coda-tocco")
        c.s.schermi = b.tool_ctx.schermi = hub2
        c.ingresso = hub2.ingresso
        tel2 = tel_di(hub2, "dario", "Dario")
        t = pr.voce_tocco("dario", "uova", sid=tel2["id"])
        t.update(schermo_creato=tel2["creato"], schermo_proprietario="dario")
        assert hub2.ingresso.metti(t)
        personale_di(hub2, tel2["id"], "bianca", "Bianca")
        loop2 = CicloFinto()
        conn2, _ = hub2.collega(riga(hub2, tel2["id"]), loop2)
        c.giro()
        if c.rec is not None:
            c._scrivi_turno(c.rec)
            c.rec = None
        verifica("coda: il tocco di Dario in coda non manda la lista né l'esito allo schermo di Bianca",
                 not loop2.arrivati and not hub2.storia(tel2["id"]), str(loop2.arrivati)[:300])
        verifica("coda: il tocco in sé vale (era di Dario, dal suo schermo, quando l'ha fatto)",
                 "uova" not in liste.read("spesa")[1], str(liste.read("spesa")[1]))
        # Contrario: il tocco di Bianca con l'identità di adesso
        t2 = pr.voce_tocco("bianca", "pane", sid=tel2["id"])
        t2.update(schermo_creato=tel2["creato"], schermo_proprietario="bianca")
        pr.tocca(c, t2)
        verifica("contrario: il tocco di Bianca dal suo schermo manda la lista e l'esito",
                 "tocco" in loop2.tipi() and "scheda" in loop2.tipi(), str(loop2.arrivati)[:300])
        hub2.scollega(conn2)
    finally:
        liste.db.close()


def pagina_aperta():
    """La pagina di Dario aperta mentre lo schermo diventa di Bianca: riceve «proprietario» (svuota
    e rifà l'accesso col token, che vale ancora) e non riceve più niente."""
    hub = hub_nuovo("pagina")
    tel = tel_di(hub, "dario", "Dario")
    sid = tel["id"]
    vecchio = CicloFinto()
    conn_d, _ = hub.collega(tel, vecchio)
    personale_di(hub, sid, "bianca", "Bianca")
    nuova = riga(hub, sid)
    loop = CicloFinto()
    conn_b, storia = hub.collega(nuova, loop)
    verifica("pagina: quella di Dario riceve «proprietario», non «revocato», e non è più collegata",
             "proprietario" in vecchio.tipi() and "revocato" not in vecchio.tipi()
             and conn_d not in hub._conn.get(sid, []) and conn_b in hub._conn.get(sid, []),
             f"{vecchio.arrivati} {hub._conn.get(sid)}")
    hub.invia(dict(NOTA, chiave="nota:bianca", testo="di Bianca"),
              Mittente(persona="bianca", nome="Bianca", livello="familiare", certo=True), forza=True)
    verifica("pagina: la scheda di Bianca arriva alla sua pagina, non a quella vecchia",
             loop.con("nota:bianca") and not vecchio.con("nota:bianca"), f"{loop.arrivati} {vecchio.arrivati}")
    verifica("pagina: valido() e schermo() col proprietario di prima no, con quello di adesso sì",
             not hub.valido(sid, tel["creato"], "dario") and hub.valido(sid, tel["creato"], "bianca")
             and hub.schermo(sid, tel["creato"], "dario") is None
             and hub.schermo(sid, tel["creato"], None) is None and hub.valido(sid))
    hub.scollega(conn_b)
    # Una pagina con l'elenco vecchio in mano (letto prima del cambio) che si collega dopo
    hub.invia_a(sid, dict(NOTA, chiave="nota:b2", testo="di Bianca"))
    vecchia_riga = dict(nuova, proprietario="dario", proprietario_nome="Dario")
    tardi = CicloFinto()
    conn_t, storia_t = hub.collega(vecchia_riga, tardi)
    verifica("pagina: una pagina con la riga di prima non riceve la cronologia e rifà l'accesso",
             storia_t == [] and "proprietario" in tardi.tipi(), f"{storia_t} {tardi.arrivati}")
    hub.scollega(conn_t)


def corsa():
    """La corsa fra `abbinati()` e il lock: un altro thread cambia il proprietario proprio lì."""
    hub = hub_nuovo("corsa")
    dario = Mittente(persona="dario", nome="Dario", livello="amministra", certo=True)
    for nome in ("invia", "invia_a", "_a_personali"):
        tel = tel_di(hub, "dario", "Dario")
        vero = Schermi.abbinati
        stato = {"fatto": False}

        def abbinati_in_corsa(self=hub, tel=tel, stato=stato, vero=vero):
            righe = vero(self)
            if not stato["fatto"]:
                stato["fatto"] = True
                personale_di(self, tel["id"], "bianca", "Bianca")
                stato["loop"] = CicloFinto()
                stato["conn"], _ = self.collega(next(s for s in vero(self) if s["id"] == tel["id"]),
                                                stato["loop"])
            return righe
        hub.abbinati = abbinati_in_corsa
        try:
            if nome == "invia":
                hub.invia(dict(NOTA), dario, forza=True)
            elif nome == "invia_a":
                hub.invia_a(tel["id"], dict(NOTA))
            else:
                hub._a_personali("dario", "chat", json.dumps({"turni": [{"id": 1, "testo": "di Dario"}]}))
        finally:
            del hub.abbinati
        verifica(f"corsa ({nome}): ciò che è di Dario non arriva allo schermo diventato di Bianca",
                 not stato["loop"].con("di Dario") and not con_storia(hub, tel["id"], "nota:dario"),
                 f"{stato['loop'].arrivati} {[x.get('chiave') for x in hub.storia(tel['id'])]}")
        hub.scollega(stato["conn"])
    # Contrario: senza corsa arriva
    tel = tel_di(hub, "dario", "Dario")
    loop = CicloFinto()
    conn, _ = hub.collega(tel, loop)
    hub.invia(dict(NOTA, chiave="nota:q"), dario, forza=True)
    hub._a_personali("dario", "chat", json.dumps({"turni": [{"id": 2, "testo": "turno di Dario"}]}))
    verifica("contrario: senza corsa la scheda e il turno arrivano allo schermo di Dario",
             loop.con("nota:q") and loop.con("turno di Dario"), str(loop.arrivati)[:300])
    hub.scollega(conn)


# ─────────────────────────── 2. i due difetti bassi ───────────────────────────
def elenco_dopo_identita():
    """`abbinati()` pubblica l'elenco nuovo solo dopo aver aggiornato le identità: una scheda per lo
    schermo riabbinato, mandata da un altro thread proprio in quell'istante, arriva."""
    hub = hub_nuovo("ordine")
    terminale = ArchivioSchermi(hub.archivio.path)
    tel = tel_di(hub, "dario", "Dario")
    sid = tel["id"]
    assert terminale.revoca(sid)
    nuovo, _ = terminale.crea_con_token("telefono", proprietario="bianca", proprietario_nome="Bianca")
    assert nuovo["id"] == sid
    loop = CicloFinto()
    conn = None
    vero = hub._identita_cambiate
    esito = {}

    def in_mezzo(*a, **k):
        # Un altro thread manda la scheda proprio mentre questo aggiorna le identità
        if "fatto" not in esito:
            esito["fatto"] = True
            esito["invia_a"] = hub.invia_a(sid, {"tipo": "testo", "chiave": "nota:legittima",
                                                 "visibilita": "personale", "testo": "di Bianca"})
        return vero(*a, **k)
    hub._identita_cambiate = in_mezzo
    hub._rinfresca()
    try:
        hub.abbinati()
    finally:
        del hub._identita_cambiate
    conn, storia = hub.collega(riga(hub, sid), loop)
    verifica("ordine: la scheda per lo schermo riabbinato mandata durante il riabbinamento non si perde",
             bool([x for x in storia if x.get("chiave") == "nota:legittima"]),
             f"{esito} {[x.get('chiave') for x in storia]}")
    hub.scollega(conn)


def aggiorna_origine():
    """L'aggiornamento della scheda pubblica del tocco va allo schermo d'origine solo se è ancora
    quello del tocco (istante e proprietario)."""
    hub = hub_nuovo("aggiorna")
    terminale = ArchivioSchermi(hub.archivio.path)
    hub.archivio.crea_con_token("cucina")
    tel = tel_di(hub, "dario", "Dario")
    sid = tel["id"]
    assert terminale.revoca(sid)
    terminale.crea_con_token("telefono", proprietario="bianca", proprietario_nome="Bianca")
    hub._rinfresca()
    timer = {"tipo": "timer", "chiave": "timer:1-1", "visibilita": "pubblica", "testo": "pasta"}
    m = Mittente(persona="lia", nome="Lia", livello="familiare", certo=True, schermo=sid)
    m.schermo_identita = {"creato": tel["creato"], "proprietario": "dario"}
    r = hub.aggiorna(dict(timer), m)
    verifica("aggiorna: il timer del tocco dello schermo revocato non va al telefono nuovo col suo numero",
             not con_storia(hub, sid, "timer:1-1"), f"{r} {hub.storia(sid)}")
    personale_di(hub, sid, "bianca", "Bianca")
    m2 = Mittente(persona="lia", nome="Lia", livello="familiare", certo=True, schermo=sid,
                  **({"schermo_identita": {"creato": riga(hub, sid)["creato"], "proprietario": "bianca"}}))
    hub.aggiorna(dict(timer, chiave="timer:1-2"), m2)
    verifica("contrario: con l'identità di adesso il timer va allo schermo del tocco",
             bool(con_storia(hub, sid, "timer:1-2")))
    # Il ciclo passa l'identità dello schermo d'origine al mittente
    b, c, sc, liste, turni, voce, finto, _ = pr.prepara_ciclo()
    try:
        visti = []
        finto.aggiorna = lambda scheda, mitt: visti.append(mitt)
        c._scheda_pubblica_del_tocco(finto, sid, dict(timer), {"persona": "bianca", "schermo_id": sid,
                                                               "schermo_creato": 5.0,
                                                               "schermo_proprietario": "bianca"}, "familiare")
        verifica("aggiorna: il ciclo dà al mittente l'identità dello schermo del tocco",
                 visti and getattr(visti[0], "schermo_identita", None) == {"creato": 5.0, "proprietario": "bianca"},
                 str(visti))
    finally:
        liste.db.close()


# ─────────────────────────── 3. per_schermo ───────────────────────────
def per_schermo():
    hub = hub_nuovo("per-schermo")
    terminale = ArchivioSchermi(hub.archivio.path)
    s, _ = hub.archivio.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario",
                                       satellite=1)
    hub._rinfresca()
    srv, coll = satellite_finto(hub, s["id"], "dario", "Dario")
    verifica("per_schermo: il satellite che ha aperto lo schermo risponde per lui",
             srv.per_schermo(s["id"]) is coll)
    assert terminale.revoca(s["id"])
    nuovo, _ = terminale.crea_con_token("telefono", proprietario="bianca", proprietario_nome="Bianca")
    assert nuovo["id"] == s["id"]
    hub._rinfresca()
    verifica("per_schermo: col numero riusato da un telefono nuovo il satellite di prima non risponde",
             srv.per_schermo(s["id"]) is None)
    # Il satellite di prima diventa della stanza: il telefono nuovo di Bianca col suo numero non cambia
    coll.satellite = dict(coll.satellite, proprietario=None, proprietario_nome=None)
    srv._allinea_schermo(coll)
    verifica("_allinea_schermo: il satellite di prima non cambia il proprietario dello schermo col suo numero",
             riga(hub, s["id"])["proprietario"] == "bianca", str(riga(hub, s["id"])))


# ─────────────────────────── 4. i contrari ───────────────────────────
def contrari():
    hub = hub_nuovo("contrari")
    tel = tel_di(hub, "dario", "Dario", stanza="studio", satellite=1)
    sid = tel["id"]
    hub.invia_a(sid, dict(NOTA))
    loop = CicloFinto()
    conn, storia = hub.collega(tel, loop)
    verifica("contrario: al collegamento la scheda di Dario torna alla sua pagina",
             [x for x in storia if x.get("chiave") == "nota:dario"])
    # Ricollegamento e flusso riaperto: stessa riga
    hub.scollega(conn)
    conn, storia = hub.collega(riga(hub, sid), loop)
    verifica("contrario: ricollegata (flusso SSE riaperto) la pagina ritrova la scheda",
             [x for x in storia if x.get("chiave") == "nota:dario"])
    # Token rinnovato (il satellite aveva perso il suo): stesso schermo
    assert hub.archivio.rinnova_token(sid)
    hub._rinfresca()
    hub.abbinati()
    verifica("contrario: col token rinnovato la cronologia e la pagina restano",
             con_storia(hub, sid, "nota:dario") and conn in hub._conn.get(sid, [])
             and "proprietario" not in loop.tipi(), str(loop.arrivati))
    # Lo stesso proprietario rimesso: dall'archivio, dal tool, dal satellite
    personale_di(hub, sid, "dario", "Dario")
    hub.abbinati()
    _, r2 = tool_personale(hub, "studio", "io")
    srv, coll = satellite_finto(hub, sid, "dario", "Dario")
    srv._allinea_schermo(coll)
    hub.abbinati()
    verifica("contrario: lo stesso proprietario rimesso (archivio, tool, satellite) non tocca niente",
             con_storia(hub, sid, "nota:dario") and conn in hub._conn.get(sid, [])
             and "proprietario" not in loop.tipi() and "già personale" in str(r2), f"{loop.arrivati} {r2}")
    n = len(loop.arrivati)
    hub.invia_a(sid, dict(NOTA, chiave="nota:dopo"), creato=tel["creato"], proprietario="dario")
    verifica("contrario: l'elemento in coda con la sua identità arriva",
             len(loop.arrivati) == n + 1 and loop.con("nota:dopo"))
    hub.scollega(conn)
    # Da condiviso a personale e ritorno: la pagina rifà l'accesso, le schede di stanza non restano
    cucina, _ = hub.archivio.crea_con_token("cucina")
    hub._rinfresca()
    hub.invia_a(cucina["id"], {"tipo": "testo", "chiave": "nota:stanza", "visibilita": "pubblica", "testo": "x"})
    lc = CicloFinto()
    cc, _ = hub.collega(riga(hub, cucina["id"]), lc)
    personale_di(hub, cucina["id"], "bianca", "Bianca")
    hub.abbinati()
    verifica("condiviso → personale: la pagina della stanza rifà l'accesso e la cronologia riparte vuota",
             "proprietario" in lc.tipi() and not hub.storia(cucina["id"]), str(lc.arrivati))
    hub.scollega(cc)


# ─────────────────────────── 5. il server vero ───────────────────────────
def leggi_eventi(port, sess, quanti, timeout=8.0):
    """I primi `quanti` eventi del flusso SSE (tipo, dati), o meno se il flusso si chiude."""
    con = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    con.request("GET", f"/eventi?sessione={sess}")
    r = con.getresponse()
    out, tipo, fine = [], None, time.monotonic() + timeout
    try:
        while len(out) < quanti and time.monotonic() < fine:
            linea = r.fp.readline()
            if not linea:
                break
            linea = linea.decode("utf-8").rstrip("\n")
            if linea.startswith("event: "):
                tipo = linea[7:]
            elif linea.startswith("data: ") and tipo:
                out.append((tipo, linea[6:]))
                tipo = None
    finally:
        con.close()
    return out


def server():
    hub = hub_nuovo("server")
    srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
    hub.server = srv
    try:
        r, tok = hub.archivio.crea_con_token("telefono", proprietario="dario", proprietario_nome="Dario")
        hub._rinfresca()
        port = srv.port
        sess = pr.chiedi(port, "/api/accedi", token=tok)[1].get("sessione")
        st, d = pr.chiedi(port, "/api/scrivi", sess, corpo={"testo": "che ho in agenda?"})
        item = hub.ingresso.prendi() or {}
        verifica("server: lo scritto in coda porta anche il proprietario dello schermo",
                 st == 200 and item.get("schermo_proprietario") == "dario"
                 and di_quale_schermo(item) == {"creato": r["creato"], "proprietario": "dario"},
                 f"{st} {d} {item}")
        hub.invia_a(r["id"], dict(NOTA))
        risultato = {}

        def apri():
            risultato["eventi"] = leggi_eventi(port, sess, 3)
        t = threading.Thread(target=apri, daemon=True)
        t.start()
        fine = time.monotonic() + 5
        while not hub.collegato(r["id"]) and time.monotonic() < fine:
            time.sleep(0.02)
        personale_di(hub, r["id"], "bianca", "Bianca")
        hub.abbinati()
        t.join(10)
        tipi = [x[0] for x in risultato.get("eventi", [])]
        verifica("server: il flusso aperto di Dario riceve «proprietario» e si chiude",
                 tipi[:1] == ["benvenuto"] and "proprietario" in tipi and "revocato" not in tipi
                 and tipi[-1] == "proprietario", str(risultato))
        sess_b = pr.chiedi(port, "/api/accedi", token=tok)[1].get("sessione")
        ev = leggi_eventi(port, sess_b, 1)
        benv = json.loads(ev[0][1]) if ev and ev[0][0] == "benvenuto" else {}
        verifica("server: il token vale ancora e il benvenuto di Bianca non ha la scheda di Dario",
                 benv.get("personale") is True
                 and not [c for c in benv.get("cronologia") or [] if c.get("chiave") == "nota:dario"],
                 str(ev)[:300])
    finally:
        srv.ferma()


def pagina_js():
    js = (Path(__file__).resolve().parent.parent / "calliope" / "schermi" / "pagina" / "schermo.js").read_text(
        encoding="utf-8")
    verifica("pagina: schermo.js gestisce «proprietario» (svuota senza togliere il token, rifà l'accesso)",
             'addEventListener("proprietario"' in js)


def main():
    parti = [("1. la riproduzione", (collegamento, coda, pagina_aperta, corsa)),
             ("2. i due difetti bassi", (elenco_dopo_identita, aggiorna_origine)),
             ("3. per_schermo", (per_schermo,)),
             ("4. i contrari", (contrari,)),
             ("5. il server", (server, pagina_js))]
    try:
        for titolo, prove in parti:
            print("— " + titolo)
            for f in prove:
                try:
                    f()
                except Exception as e:  # noqa: BLE001 — una parte che solleva è un errore, le altre vanno
                    verifica(f"{f.__name__}: senza eccezioni", False, f"{type(e).__name__}: {e}")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(ERRORI)} errori" if ERRORI else "\ntutto ok")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
