"""Prova a secco dell'aspetto dei satelliti personali (27/10/2026, passo 1c di
docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md, issue #240; area
docs/aree/schermi-telefono.md).

1. **Gli accenti** (`schermi/aspetto.ACCENTI`): il lilla di serie; ogni accento ha la sua famiglia
   completa di colori #rrggbb e la terna RGB uguale all'accento; contrasto AA (≥ 4,5:1)
   dell'accento sul nero e sui pannelli, del testo sopra l'accento, dell'accento chiaro e
   dell'accento sul fondo tinto. Il lilla di serie dei CSS (schermo.css) è quello della tabella.
2. **Sezioni per età** (`aspetto.nascoste`): un adulto niente; un minore di 12 anni Casa e Ufficio;
   il giorno del tredicesimo compleanno solo Ufficio (il giorno prima ancora Casa); un minore senza
   data di nascita (fascia scritta a mano) Casa e Ufficio; nessun profilo niente.
3. **La preferenza** (`PreferenzeAspetto`): di serie il lilla; salvata, resta dopo la riapertura;
   un accento sconosciuto non si salva; «svuota» della persona (conserva) la toglie, quella di
   un'altra persona resta.
4. **Il server** (server degli schermi vero su 127.0.0.1): `/api/accedi` dà l'accento (con le
   scelte solo sugli schermi personali; uno schermo di stanza resta lilla) e le sezioni nascoste
   dal profilo del proprietario, letto a ogni accesso; `/api/aspetto` sceglie da uno schermo
   personale (403 da quello di stanza, 400 per un accento sconosciuto, 401 senza sessione) e
   manda l'evento «aspetto» a tutte le pagine della persona, non a quelle degli altri.

    python prove/prova_aspetto.py
"""

import datetime
import json
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from calliope.config import Config
from calliope.schermi import ArchivioSchermi, Schermi
from calliope.schermi import aspetto as A
from calliope.schermi.server import ServerSchermi

RADICE = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="calliope-aspetto-"))
ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


def lum(esa: str) -> float:
    r, g, b = (int(esa[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in (r, g, b)]
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2]


def contrasto(a: str, b: str) -> float:
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def accenti():
    verifica("accenti: il lilla è quello di serie", A.DI_SERIE == "lilla" and "lilla" in A.ACCENTI
             and "oro" in A.ACCENTI and len(A.ACCENTI) >= 3)
    chiavi = {"nome", "accento", "chiaro", "bordo", "selezione", "fondo", "su", "tenue"}
    for nome, a in A.ACCENTI.items():
        forme = set(a) == chiavi and all(re.fullmatch(r"#[0-9a-f]{6}", a[k])
                                         for k in chiavi - {"nome", "tenue"})
        rgb = ", ".join(str(int(a["accento"][i:i + 2], 16)) for i in (1, 3, 5))
        verifica(f"accenti: {nome} ha tutti i colori e la terna dell'accento", forme and a["tenue"] == rgb,
                 json.dumps(a))
        if not forme:
            continue
        coppie = {"accento sul nero": (a["accento"], "#000000"),
                  "accento sul pannello del telefono": (a["accento"], "#0d0d0d"),
                  "accento sul pannello degli schermi": (a["accento"], "#171a21"),
                  "testo sopra l'accento": (a["su"], a["accento"]),
                  "accento chiaro sul fondo tinto": (a["chiaro"], a["fondo"]),
                  "accento sul fondo tinto": (a["accento"], a["fondo"])}
        bassi = {k: round(contrasto(*v), 2) for k, v in coppie.items() if contrasto(*v) < 4.5}
        verifica(f"accenti: {nome} con contrasto AA (≥ 4,5:1)", not bassi, json.dumps(bassi))
    css = (RADICE / "calliope" / "schermi" / "pagina" / "schermo.css").read_text(encoding="utf-8")
    l = A.ACCENTI["lilla"]
    verifica("accenti: il lilla dei CSS è quello della tabella",
             f"--accento: {l['accento']};" in css and f"--su-accento: {l['su']};" in css
             and f"--accento-rgb: {l['tenue']};" in css and f"--accento-fondo: {l['fondo']};" in css)
    p = A.per_pagina("rosa", True)
    verifica("per la pagina: accento, colori e scelte (solo personale)",
             p["accento"] == "rosa" and p["colori"]["accento"] == A.ACCENTI["rosa"]["accento"]
             and len(p["scelte"]) == len(A.ACCENTI) and "scelte" not in A.per_pagina("rosa", False))
    verifica("per la pagina: un nome sconosciuto è il lilla", A.per_pagina("viola!", False)["accento"] == "lilla")


class Profilo:
    def __init__(self, pid, nome, nascita=None, fascia=None, admin=False):
        self.id, self.name, self.nascita, self.fascia, self.admin = pid, nome, nascita, fascia, admin


def eta():
    oggi = datetime.date(2026, 10, 27)
    casi = [
        ("adulto", Profilo("a", "Ada", "1980-05-01"), [], []),
        ("12 anni", Profilo("b", "Bice", "2014-03-10"), ["casa"], ["ufficio"]),
        ("il giorno prima dei 13", Profilo("c", "Ciro", "2013-10-28"), ["casa"], ["ufficio"]),
        ("il giorno dei 13", Profilo("d", "Dora", "2013-10-27"), [], ["ufficio"]),
        ("17 anni", Profilo("e", "Elio", "2009-01-01"), [], ["ufficio"]),
        ("senza data, fascia a mano", Profilo("f", "Fede", None, "bambini"), ["casa"], ["ufficio"]),
    ]
    for nome, prof, sez, racc in casi:
        n = A.nascoste(prof, oggi)
        verifica(f"età: {nome}", n == {"sezioni": sez, "raccolte": racc}, json.dumps(n))
    verifica("età: senza profilo niente di nascosto", A.nascoste(None, oggi) == {"sezioni": [], "raccolte": []})


def preferenze():
    db = str(TMP / "pref.db")
    p = A.PreferenzeAspetto(db)
    verifica("preferenza: di serie il lilla", p.accento("bice") == "lilla" and p.accento(None) == "lilla")
    verifica("preferenza: un accento sconosciuto non si salva", p.salva("bice", "nero") is False
             and p.accento("bice") == "lilla")
    p.salva("bice", "rosa")
    p.salva("ugo", "oro")
    p.close()
    p = A.PreferenzeAspetto(db)
    verifica("preferenza: salvata, resta dopo la riapertura", p.accento("bice") == "rosa")
    p.close()
    # «svuota» della persona (conserva.py, TABELLE_PREFERENZE)
    from calliope.conserva import Conservazione
    cfg = Config()
    cfg.memory_db = db
    cfg.turn_log_dir = str(TMP / "registro")
    c = Conservazione(cfg, None, log=lambda m: None)
    n = c._memoria(persona_id="bice")
    p = A.PreferenzeAspetto(db)
    verifica("preferenza: «svuota» della persona la toglie, quella di un altro resta",
             n >= 1 and p.accento("bice") == "lilla" and p.accento("ugo") == "oro", str(n))
    p.close()


def chiedi(port, percorso, sessione=None, token=None, corpo=None):
    h = {"Content-Type": "application/json"}
    if sessione:
        h["X-Calliope-Sessione"] = sessione
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(f"http://127.0.0.1:{port}{percorso}", headers=h, method="POST",
                                 data=json.dumps(corpo or {}).encode("utf-8"))
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def server():
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "memoria.db")
    profili = {"dario": Profilo("dario", "Dario", "1978-02-02", admin=True),
               "bice": Profilo("bice", "Bice", "2016-04-04")}
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    hub.profilo = profili.get
    srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
    hub.server = srv
    try:
        arch = hub.archivio
        _, t_dario = arch.crea_con_token("telefono", proprietario="dario", proprietario_nome="Dario")
        _, t_dario2 = arch.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario")
        _, t_bice = arch.crea_con_token("cameretta", proprietario="bice", proprietario_nome="Bice")
        _, t_cucina = arch.crea_con_token("cucina")
        hub._rinfresca()
        port = srv.port
        st, d = chiedi(port, "/api/accedi", token=t_dario)
        a = d.get("aspetto") or {}
        verifica("accedi: lo schermo personale riceve il lilla di serie con le scelte",
                 st == 200 and a.get("accento") == "lilla" and len(a.get("scelte") or []) == len(A.ACCENTI)
                 and d.get("nascoste") == {"sezioni": [], "raccolte": []}, json.dumps(d)[:300])
        sess = d.get("sessione")
        st, c = chiedi(port, "/api/accedi", token=t_cucina)
        verifica("accedi: lo schermo di stanza resta lilla, senza scelte né sezioni nascoste",
                 (c.get("aspetto") or {}).get("accento") == "lilla" and "scelte" not in (c.get("aspetto") or {})
                 and c.get("nascoste") == {"sezioni": [], "raccolte": []}, json.dumps(c.get("aspetto")))
        st, b = chiedi(port, "/api/accedi", token=t_bice)
        verifica("accedi: il telefono di una bambina di 10 anni senza Casa né Ufficio",
                 b.get("nascoste") == {"sezioni": ["casa"], "raccolte": ["ufficio"]}, json.dumps(b.get("nascoste")))
        # Le pagine aperte: due di Dario, una di Bice (le code delle connessioni, come l'SSE)
        import asyncio
        from calliope.schermi.hub import _Connessione
        ciclo = asyncio.new_event_loop()
        conns = {}
        for tok, chi in ((t_dario, "dario1"), (t_dario2, "dario2"), (t_bice, "bice")):
            s = arch.per_token(tok)
            conn = _Connessione(s, ciclo)
            hub._conn.setdefault(s["id"], []).append(conn)
            conns[chi] = conn
        st, r = chiedi(port, "/api/aspetto", sessione=sess, corpo={"accento": "rosa"})
        ciclo.run_until_complete(asyncio.sleep(0.05))

        def eventi(conn):
            out = []
            while not conn.coda.empty():
                out.append(conn.coda.get_nowait())
            return [(t, json.loads(m)) for t, m in out if t == "aspetto"]
        e1, e2, e3 = eventi(conns["dario1"]), eventi(conns["dario2"]), eventi(conns["bice"])
        verifica("aspetto: scelto dallo schermo personale, salvato",
                 st == 200 and r.get("ok") and r["aspetto"]["accento"] == "rosa"
                 and hub.aspetto.accento("dario") == "rosa", json.dumps(r)[:200])
        verifica("aspetto: l'evento va a tutte le pagine di Dario, non a quelle di Bice",
                 len(e1) == 1 and len(e2) == 1 and e1[0][1]["accento"] == "rosa" and not e3,
                 json.dumps([len(e1), len(e2), len(e3)]))
        st, d2 = chiedi(port, "/api/accedi", token=t_dario2)
        verifica("accedi: l'altro schermo di Dario ha l'accento scelto",
                 (d2.get("aspetto") or {}).get("accento") == "rosa")
        st, c2 = chiedi(port, "/api/accedi", token=t_cucina)
        verifica("accedi: lo schermo di stanza resta lilla dopo la scelta di Dario",
                 (c2.get("aspetto") or {}).get("accento") == "lilla")
        st, r = chiedi(port, "/api/aspetto", sessione=c.get("sessione"), corpo={"accento": "oro"})
        verifica("aspetto: da uno schermo di stanza no (403)", st == 403, f"{st} {r}")
        st, r = chiedi(port, "/api/aspetto", sessione=sess, corpo={"accento": "#ff0000"})
        verifica("aspetto: un accento sconosciuto no (400), resta quello di prima",
                 st == 400 and hub.aspetto.accento("dario") == "rosa", f"{st} {r}")
        st, r = chiedi(port, "/api/aspetto", sessione="inventata", corpo={"accento": "oro"})
        verifica("aspetto: senza sessione no (401)", st == 401, str(st))
        # Il profilo letto a ogni accesso: Bice compie 13 anni (nascita spostata)
        profili["bice"].nascita = "2013-01-01"
        st, b2 = chiedi(port, "/api/accedi", token=t_bice)
        verifica("accedi: il profilo si rilegge (13 anni: Casa sì, Ufficio no)",
                 b2.get("nascoste") == {"sezioni": [], "raccolte": ["ufficio"]}, json.dumps(b2.get("nascoste")))
        ciclo.close()
    finally:
        srv.ferma()


def main() -> int:
    try:
        accenti()
        eta()
        preferenze()
        server()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
