import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""SearXNG tenuto aggiornato (09/10/2026, calliope/web/motore.py e setup/linux/motore/searxng.sh),
a secco: SearXNG, registro delle immagini e docker finti, niente rete vera.

- prove e giudizio: «buona», «degradata» (pochi risultati, motori o risultati sotto la soglia
  dell'ultimo buono), «giù»; «almeno come» con la tolleranza; righe di prova sbagliate saltate;
- registro delle immagini: mai «latest», solo tag di data con digest e arm64+amd64, attivi, in
  ordine; la scelta del tag (età minima, degradata, scartati, manuale, niente di più nuovo);
- aggiornamento con docker finto: nuova migliore → tenuta, pulizia delle vecchie, avviso; nuova
  peggiore alla prova accanto → resta la vecchia senza fermare niente, tag scartato; peggiore
  dopo il cambio → ritorno indietro; scaricamento non riuscito → resta la vecchia;
- automatico: niente con Calliope in uso o lavori in corso o controllo recente; a Calliope
  ferma controllo e aggiornamento; modo manuale: solo il controllo, aggiornamento a richiesta
  (rifiutato con lavori in corso); un'operazione alla volta (anche tra processi);
- registro delle capacità: «degradata» con motivo e passo, «cosa sai fare?» la conta come
  funzionante; Windows (qui): controllo sì, aggiornamento spento con il perché;
- cruscotto: sezione solo con il motore, gettoni (schermo, azione, scadenza, una volta), limite
  al minuto, endpoint /api/motore solo per chi amministra, avviso solo agli schermi personali
  di chi amministra;
- lo script con bash e docker finti (se c'è un bash di Git): immagine scelta o fissata, forma
  dell'immagine (mai latest), copia di prova sulla sua porta, «usa», pulizia solo delle immagini
  scaricate da qui.
"""

import json
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from calliope import capacita
from calliope.config import Config
from calliope.web import motore as M

TMP = Path(tempfile.mkdtemp(prefix="calliope-searxng-agg-"))
ERRORI = []
DIG = {n: "sha256:" + (f"{n:x}" * 64)[:64] for n in range(1, 10)}
VECCHIA = f"searxng/searxng:2026.10.2-19ffbcd30@{DIG[1]}"
NUOVA = f"searxng/searxng:2026.10.7-6671d89be@{DIG[2]}"
GIORNO = 86400.0


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


# ─────────────────────────── finti ───────────────────────────

class Risposta:
    def __init__(self, stato, dati):
        self.status_code, self._dati = stato, dati

    def json(self):
        return self._dati


def risposta_searxng(n, motori=("bing", "duckduckgo", "brave"), giu=()):
    res = [{"url": f"https://sito{i}.example/{i}", "title": f"t{i}",
            "engines": [motori[i % len(motori)]]} for i in range(n)]
    return {"results": res, "unresponsive_engines": [list(g) for g in giu]}


class HttpFinto:
    """SearXNG per indirizzo: `profili[url]` = (n risultati, motori, giu) o "giu"; il registro
    delle immagini a `registro`."""

    def __init__(self, registro_dati=None):
        self.profili = {}
        self.registro_dati = registro_dati or {"results": []}
        self.chiamate = []

    def post(self, url, data=None, timeout=None, headers=None):
        base = url.rsplit("/search", 1)[0]
        self.chiamate.append(("POST", base, dict(data or {})))
        p = self.profili.get(base, "giu")
        if p == "giu":
            raise ConnectionError("rifiutata")
        n, motori, giu = p
        if isinstance(n, dict):
            n = n.get(data.get("categories"), 0)
        return Risposta(200, risposta_searxng(n, motori, giu))

    def get(self, url, timeout=None, headers=None):
        self.chiamate.append(("GET", url, None))
        if self.registro_dati == "giu":
            raise ConnectionError("registro giù")
        return Risposta(200, self.registro_dati)


def tag(nome, digest, giorni_fa, archi=("amd64", "arm64", "arm"), stato="active", ora=None):
    ora = ora or time.time()
    quando = time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime(ora - giorni_fa * GIORNO))
    return {"name": nome, "digest": digest, "tag_status": stato, "last_updated": quando,
            "tag_last_pushed": quando, "images": [{"architecture": a} for a in archi]}


class ScriptFinto:
    """searxng.sh finto: l'immagine in uso cambia con «usa»; `candidata_ok`, `usa_ok`."""

    def __init__(self, in_uso=VECCHIA, porta_prova=10004):
        self.in_uso = in_uso
        self.chiamate = []
        self.candidata_ok = True
        self.usa_ok = lambda img: True
        self.porta_prova = porta_prova
        self.durante_usa = None

    def __call__(self, *args, timeout=0):
        self.chiamate.append(args)
        az = args[0]
        if az == "immagine":
            return 0, self.in_uso
        if az == "candidata":
            return (0, f"http://127.0.0.1:{self.porta_prova}") if self.candidata_ok else (1, "pull non riuscito")
        if az == "usa":
            if self.durante_usa:
                self.durante_usa(args[1])
            if self.usa_ok(args[1]):
                self.in_uso = args[1]
                return 0, "risponde"
            return 1, "non risponde"
        return 0, ""

    def azioni(self):
        return [c[0] + (" " + M.tag_di(c[1]) if len(c) > 1 and M.tag_di(c[1]) else "")
                for c in self.chiamate if c[0] != "immagine"]


def cfg_di(nome, **kw):
    cfg = Config()
    cfg.web_searxng_url = "http://127.0.0.1:8004"
    cfg.web_searxng_stato = str(TMP / nome / "searxng.json")
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def motore(nome, http, script, avvisi=None, **kw):
    cfg = cfg_di(nome, **{k: v for k, v in kw.items() if k.startswith("web_")})
    altri = {k: v for k, v in kw.items() if not k.startswith("web_")}
    altri.setdefault("attendi", lambda s: None)
    return M.MotoreRicerca(cfg, http=http, script=script, log=lambda m: None,
                           avvisa=(lambda t, x: avvisi.append((t, x))) if avvisi is not None else None,
                           controllabile=True, aggiornabile=True, **altri)


BUONO = (8, ("bing", "duckduckgo", "brave", "startpage"), ())
SCARSO = (1, ("bing",), (("brave", "CAPTCHA"), ("duckduckgo", "timeout")))


# ─────────────────────────── prove ───────────────────────────

def prova_giudizio():
    cfg = Config()
    verifica("prove predefinite: generale, notizie, a tema", [c for c, _ in M.prove_da(cfg)]
             == ["general", "news", "news"], M.prove_da(cfg))
    cfg.web_searxng_prove = ["news:Serie A", "sbagliata", "pippo:x y", "general:  meteo  Roma "]
    verifica("righe di prova sbagliate saltate", M.prove_da(cfg) == [("news", "Serie A"),
                                                                    ("general", "meteo Roma")],
             M.prove_da(cfg))
    h = HttpFinto()
    h.profili["http://s"] = BUONO
    buono = M.misura("http://s", [("general", "a"), ("news", "b")], h)
    verifica("misura: risultati, motori, tempi", buono["risultati"] == 16 and len(buono["motori"]) == 4
             and buono["risposte"] == 2, buono["risultati"])
    verifica("misura in POST con format json e categoria", h.chiamate[0][2].get("format") == "json"
             and h.chiamate[1][2].get("categories") == "news")
    verifica("giudizio: buona", M.giudica(buono, None)[0] == "buona")
    h.profili["http://s"] = SCARSO
    scarso = M.misura("http://s", [("general", "a")], h)
    st, mot = M.giudica(scarso, buono)
    verifica("giudizio: pochi risultati → degradata con i motori giù e il motivo",
             st == "degradata" and "CAPTCHA" in mot and "1 risultati" in mot, mot)
    h.profili["http://s"] = (6, ("bing", "duckduckgo"), ())
    meno = M.misura("http://s", [("general", "a"), ("news", "b")], h)
    st, mot = M.giudica(meno, buono, 3, 0.6)
    verifica("giudizio: motori sotto la soglia dell'ultimo buono → degradata",
             st == "degradata" and "2 motori contro 4" in mot, mot)
    verifica("giudizio: senza un buono precedente gli stessi numeri vanno bene",
             M.giudica(meno, None)[0] == "buona")
    h.profili.clear()
    giu = M.misura("http://s", [("general", "a")], h)
    verifica("giudizio: nessuna risposta → giù", M.giudica(giu, buono)[0] == "giù"
             and giu["prove"][0]["errore"] == "ConnectionError")
    ok, _ = M.almeno_come(buono, buono)
    verifica("almeno come: uguale → sì", ok)
    h.profili["http://s"] = (8, ("bing", "duckduckgo", "brave"), ())
    un_motore_in_meno = M.misura("http://s", [("general", "a"), ("news", "b")], h)
    verifica("almeno come: un motore in meno è rumore", M.almeno_come(un_motore_in_meno, buono)[0])
    ok, perche = M.almeno_come(meno, buono)
    verifica("almeno come: due motori in meno → no", not ok and "motori" in perche, perche)
    verifica("almeno come: la nuova non risponde → no", not M.almeno_come(giu, buono)[0])


def prova_registro():
    ora = time.time()
    dati = {"results": [
        tag("latest", DIG[3], 0, ora=ora),
        tag("2026.10.7-6671d89be", DIG[2], 2, ora=ora),
        tag("2026.10.6-aaaaaaa", DIG[4], 3, archi=("amd64",), ora=ora),
        tag("2026.10.5-bbbbbbb", "sha256:corto", 4, ora=ora),
        tag("2026.10.4-ccccccc", DIG[5], 5, stato="inactive", ora=ora),
        tag("2026.10.4-d48c4b555", DIG[6], 5, ora=ora),
        tag("2026.10.2-19ffbcd30", DIG[1], 7, ora=ora),
        tag("nightly-2026", DIG[7], 1, ora=ora)]}
    h = HttpFinto(dati)
    tags = M.tag_recenti(h, "https://registro.example/tags")
    nomi = [t["tag"] for t in tags]
    verifica("registro: mai latest, solo tag di data con digest, arm64 e amd64, attivi",
             nomi == ["2026.10.7-6671d89be", "2026.10.4-d48c4b555", "2026.10.2-19ffbcd30"], nomi)
    verifica("registro: immagine con tag e digest", tags[0]["immagine"] == NUOVA, tags[0]["immagine"])
    m = motore("scelta", h, ScriptFinto(), orologio=lambda: ora)
    verifica("scelta automatica: il più recente ha 2 giorni < 3 → quello di 5 giorni",
             (m.scegli(tags, VECCHIA, False, False) or {}).get("tag") == "2026.10.4-d48c4b555")
    verifica("scelta automatica, degradata: il più recente anche se giovane",
             (m.scegli(tags, VECCHIA, False, True) or {}).get("tag") == "2026.10.7-6671d89be")
    verifica("scelta manuale: il più recente", (m.scegli(tags, VECCHIA, True, False) or {}).get("tag")
             == "2026.10.7-6671d89be")
    verifica("niente di più nuovo di quella in uso → nessuna scelta",
             m.scegli(tags, NUOVA, True, True) is None)
    m._scarta("2026.10.4-d48c4b555")
    verifica("un tag scartato non si riprova da solo", m.scegli(tags, VECCHIA, False, False) is None)
    verifica("…a mano sì", (m.scegli(tags, VECCHIA, True, False) or {}).get("tag") == "2026.10.7-6671d89be")


def _registro_hub(ora):
    return {"results": [tag("2026.10.7-6671d89be", DIG[2], 5, ora=ora),
                        tag("2026.10.2-19ffbcd30", DIG[1], 7, ora=ora)]}


def prova_aggiornamento():
    ora = time.time()
    # Nuova migliore
    h = HttpFinto(_registro_hub(ora))
    h.profili["http://127.0.0.1:8004"] = (3, ("bing", "brave"), (("duckduckgo", "CAPTCHA"),))
    h.profili["http://127.0.0.1:10004"] = BUONO
    sc = ScriptFinto()

    def dopo_usa(img):
        if img == NUOVA:
            h.profili["http://127.0.0.1:8004"] = BUONO
    sc.durante_usa = dopo_usa
    avvisi = []
    m = motore("migliore", h, sc, avvisi)
    r = m.aggiorna("automatico")
    verifica("nuova migliore: aggiornata", r["esito"] == "aggiornata", r)
    verifica("nuova migliore: copia di prova accanto, tolta, poi «usa» e pulizia",
             sc.azioni() == ["candidata 2026.10.7-6671d89be", "togli-candidata",
                             "usa 2026.10.7-6671d89be", "pulisci-immagini 2026.10.2-19ffbcd30"],
             sc.azioni())
    st = m.leggi()
    verifica("stato: immagine nuova, giudizio buona, storia", M.tag_di(st["immagine"])
             == "2026.10.7-6671d89be" and st["giudizio"]["stato"] == "buona"
             and st["storia"][-1]["esito"] == "aggiornata")
    verifica("avviso a chi amministra (automatico)", len(avvisi) == 1 and "2026.10.7" in avvisi[0][1],
             avvisi)
    verifica("mai «latest» chiesto allo script", not any("latest" in " ".join(c) for c in sc.chiamate))

    # Nuova peggiore alla prova accanto: la vecchia non si ferma mai
    h = HttpFinto(_registro_hub(ora))
    h.profili["http://127.0.0.1:8004"] = BUONO
    h.profili["http://127.0.0.1:10004"] = SCARSO
    sc = ScriptFinto()
    avvisi = []
    m = motore("peggiore", h, sc, avvisi)
    r = m.aggiorna("automatico")
    verifica("nuova peggiore: tenuta la vecchia", r["esito"] == "tenuta" and sc.in_uso == VECCHIA, r)
    verifica("nuova peggiore: nessun «usa» (niente fermato)", "usa" not in [c[0] for c in sc.chiamate],
             sc.azioni())
    verifica("nuova peggiore: tag scartato e avviso", "2026.10.7-6671d89be" in m.leggi()["scartate"]
             and len(avvisi) == 1)
    verifica("…e l'automatico non lo riprova", m.aggiorna("automatico")["esito"] == "niente")

    # Bene accanto, male dopo il cambio: ritorno indietro
    h = HttpFinto(_registro_hub(ora))
    h.profili["http://127.0.0.1:8004"] = BUONO
    h.profili["http://127.0.0.1:10004"] = BUONO
    sc = ScriptFinto()

    def rotta(img):
        h.profili["http://127.0.0.1:8004"] = SCARSO if img == NUOVA else BUONO
    sc.durante_usa = rotta
    m = motore("indietro", h, sc, [])
    r = m.aggiorna("automatico")
    verifica("peggiore dopo il cambio: tornata indietro", r["esito"] == "indietro"
             and sc.in_uso == VECCHIA, r)
    verifica("…con «usa» della vecchia", sc.azioni()[-1] == "usa 2026.10.2-19ffbcd30", sc.azioni())

    # Il container nuovo non risponde: ritorno indietro
    sc = ScriptFinto()
    sc.usa_ok = lambda img: img != NUOVA
    m = motore("non_risponde", h, sc, [])
    h.profili["http://127.0.0.1:8004"] = BUONO
    r = m.aggiorna("automatico")
    verifica("la nuova non parte: tornata indietro", r["esito"] == "indietro" and sc.in_uso == VECCHIA, r)

    # Scaricamento non riuscito
    sc = ScriptFinto()
    sc.candidata_ok = False
    m = motore("pull", h, sc, [])
    r = m.aggiorna("automatico")
    verifica("scaricamento non riuscito: errore, la vecchia resta", r["esito"] == "errore"
             and sc.in_uso == VECCHIA and "usa" not in [c[0] for c in sc.chiamate], r)

    # Registro delle immagini giù
    h2 = HttpFinto("giu")
    m = motore("registro_giu", h2, ScriptFinto(), [])
    r = m.aggiorna("automatico")
    verifica("registro giù: errore, niente toccato", r["esito"] == "errore", r)

    # Già all'ultima (manuale)
    h = HttpFinto(_registro_hub(ora))
    h.profili["http://127.0.0.1:8004"] = BUONO
    m = motore("ultima", h, ScriptFinto(in_uso=NUOVA), [])
    r = m.aggiorna("cruscotto:dario", manuale=True)
    verifica("già all'ultima (manuale)", r["esito"] == "ultima", r)

    # L'automatico ricontrolla prima del cambio: qualcuno ha cominciato a parlare
    h = HttpFinto(_registro_hub(ora))
    h.profili["http://127.0.0.1:8004"] = BUONO
    h.profili["http://127.0.0.1:10004"] = BUONO
    sc = ScriptFinto()
    stato = {"inattiva": 4000.0}
    m = motore("rinvio", h, sc, [], inattivita=lambda: stato["inattiva"])
    vecchio_misura = m._misura

    def misura_e_parla(url, img=""):
        if url.endswith(":10004"):
            stato["inattiva"] = 5.0          # mentre provava la nuova, qualcuno parla
        return vecchio_misura(url, img)
    m._misura = misura_e_parla
    r = m.aggiorna("automatico")
    verifica("automatico: in uso durante la prova → rinviato, nessun cambio", r["esito"] == "rinviato"
             and sc.in_uso == VECCHIA, r)


def prova_automatico():
    ora = [time.time()]
    h = HttpFinto(_registro_hub(ora[0]))
    h.profili["http://127.0.0.1:8004"] = BUONO
    h.profili["http://127.0.0.1:10004"] = BUONO
    sc = ScriptFinto()
    st = {"inattiva": 60.0, "lavori": 0}
    pause = []
    m = motore("auto", h, sc, [], inattivita=lambda: st["inattiva"], lavori=lambda: st["lavori"],
               orologio=lambda: ora[0], attendi=pause.append)
    verifica("automatico: Calliope in uso → niente", m.passo() == "occupata" and not h.chiamate)
    st["inattiva"], st["lavori"] = 7200.0, 1
    verifica("automatico: lavori in corso → niente", m.passo() == "occupata" and not h.chiamate)
    st["lavori"] = 0
    r = m.passo()
    verifica("automatico: ferma e senza lavori → controllo e aggiornamento",
             r == "buona:aggiornata" and sc.in_uso == NUOVA, r)
    ricerche = [c for c in h.chiamate if c[0] == "POST"]
    verifica("poche ricerche: le prove del controllo valgono per la vecchia (9 in tutto, non 12)",
             len(ricerche) == 9, len(ricerche))
    verifica("ricerche distanziate: pause tra le prove e tra i giri",
             pause.count(M.PAUSA_PROVE_S) == 6 and pause.count(M.PAUSA_GIRI_S) == 1, pause)
    n = len(h.chiamate)
    verifica("automatico: controllo appena fatto → presto", m.passo() == "presto" and len(h.chiamate) == n)
    ora[0] += 25 * 3600
    r = m.passo()
    verifica("automatico: il giorno dopo di nuovo il controllo (già all'ultima: nessun cambio)",
             r == "buona:niente", r)

    # Modo manuale: solo il controllo
    h = HttpFinto(_registro_hub(ora[0]))
    h.profili["http://127.0.0.1:8004"] = SCARSO
    sc = ScriptFinto()
    avvisi = []
    m = motore("manuale", h, sc, avvisi, web_searxng_aggiorna="manuale",
               inattivita=lambda: 7200.0, lavori=lambda: 0)
    verifica("manuale: il controllo sì, l'aggiornamento no", m.passo() == "controllato"
             and "candidata" not in [c[0] for c in sc.chiamate]
             and not any(c[0] == "GET" for c in h.chiamate))
    verifica("manuale: degradata nel giudizio e avviso con «Aggiorna»", m.giudizio()["stato"] == "degradata"
             and avvisi and "Aggiorna" in avvisi[0][1], avvisi)
    verifica("modo sconosciuto vale manuale", motore("x", h, sc, web_searxng_aggiorna="sempre").modo
             == "manuale")

    # A richiesta (cruscotto): parte in un thread, si vede in corso, poi l'esito
    h.profili["http://127.0.0.1:10004"] = BUONO

    def migliora(img):
        if img == NUOVA:
            h.profili["http://127.0.0.1:8004"] = BUONO
    sc.durante_usa = migliora
    lavori = {"n": 1}
    m2 = motore("manuale", h, sc, avvisi, web_searxng_aggiorna="manuale", lavori=lambda: lavori["n"])
    ok, frase = m2.avvia_azione("aggiorna", "cruscotto:dario")
    verifica("a richiesta con lavori in corso: rifiutato", not ok and "lavori" in frase, frase)
    lavori["n"] = 0
    ok, frase = m2.avvia_azione("aggiorna", "cruscotto:dario")
    ok2, frase2 = m2.avvia_azione("controlla", "cruscotto:dario")
    verifica("a richiesta: parte, e un secondo tocco intanto no", ok and not ok2, (frase, frase2))
    for _ in range(100):
        if m2.in_corso is None:
            break
        time.sleep(0.05)
    v = m2.vista()
    verifica("a richiesta: esito nella vista, niente più in corso", v["in_corso"] is None
             and (v["esito"] or {}).get("esito") == "aggiornata"
             and v["esito"]["chi"] == "cruscotto:dario", v["esito"])
    verifica("a richiesta: nessun avviso in più (lo vede sulla scheda)",
             not any("Ho aggiornato" in x for _, x in avvisi), avvisi)


def prova_pause():
    """Motori in pausa (09/10 sera): il conto dei controlli falliti di fila, la pausa, la ripresa
    dopo i giorni, «degradata» con pochi motori, l'applicazione con lo script e i contrari."""
    ora = 1_800_000_000.0
    giu_brave = {"ok": True, "motori": ["duckduckgo"], "giu": [["brave", "too many requests"]]}
    esito = {"prove": [giu_brave, {"ok": True, "motori": ["ansa"], "giu": []}]}
    m, p, ev = M.aggiorna_motori({}, esito, ora, 2, 3.0)
    verifica("pause: un controllo fallito non basta", p == [] and m["brave"]["falliti"] == 1
             and not ev, m)
    m, p, ev = M.aggiorna_motori(m, esito, ora + 86400, 2, 3.0)
    verifica("pause: due di fila → in pausa con il perché", p == ["brave"]
             and ev == [("pausa", "brave", "too many requests")], (m, ev))
    verifica("pause: la frase per il registro",
             M.frase_motori(ev, m) == "metto in pausa brave (too many requests)")
    # Tutti giù nella stessa prova (manca internet?): non conta
    tutti = {"prove": [{"ok": True, "motori": [], "giu": [["duckduckgo", "timeout"],
                                                          ["qwant", "CAPTCHA"]]}]}
    m2, p2, _ = M.aggiorna_motori({}, tutti, ora, 1, 3.0)
    verifica("pause, contrario: nessun motore risponde nella prova → nessun conto", not m2 and
             not p2, m2)
    # Un motore che risponde azzera il conto
    m3, _, _ = M.aggiorna_motori({"qwant": {"falliti": 1, "perche": "CAPTCHA"}},
                                 {"prove": [{"ok": True, "motori": ["qwant", "duckduckgo"],
                                             "giu": []}]}, ora, 2, 3.0)
    verifica("pause, contrario: risponde di nuovo → conto azzerato", "qwant" not in m3, m3)
    # In giu ma con risultati in un'altra prova: non fallito
    m4, _, _ = M.aggiorna_motori({}, {"prove": [giu_brave, {"ok": True, "motori": ["brave"],
                                                             "giu": []}]}, ora, 1, 3.0)
    verifica("pause, contrario: giù in una prova, risultati in un'altra → non conta",
             "brave" not in m4, m4)
    # Dopo i giorni si riprova; un altro fallimento la rimette subito in pausa
    m5, p5, ev5 = M.aggiorna_motori(m, {"prove": [{"ok": True, "motori": ["duckduckgo"],
                                                   "giu": []}]}, ora + 5 * 86400, 2, 3.0)
    verifica("pause: dopo i giorni si riprova", p5 == [] and ev5 == [("riprovo", "brave",
                                                                      "too many requests")], ev5)
    m6, p6, _ = M.aggiorna_motori(m5, esito, ora + 6 * 86400, 2, 3.0)
    verifica("pause: e se non risponde ancora, di nuovo in pausa al primo controllo",
             p6 == ["brave"], m6)
    m7, p7, ev7 = M.aggiorna_motori(m, esito, ora + 86400, 0, 3.0)
    verifica("pause, contrario: 0 controlli = mai in pausa (e le pause tolte)", p7 == [] and
             ev7 and ev7[0][0] == "riprovo", ev7)

    # Con il motore: il controllo che fallisce due volte mette in pausa (lo script), lo stato
    h = HttpFinto()
    h.profili["http://127.0.0.1:8004"] = (8, ("duckduckgo", "startpage", "qwant", "ansa"),
                                          (("brave", "too many requests"),
                                           ("wikidata", "timeout")))
    sc = ScriptFinto()
    orologio = [ora]
    mr = motore("pause", h, sc, [], orologio=lambda: orologio[0])
    mr.controlla("terminale")
    verifica("motore: al primo controllo nessuna pausa", not any(c[0] == "pausa"
                                                                 for c in sc.chiamate))
    orologio[0] += 86400
    mr.controlla("terminale")
    verifica("motore: al secondo, searxng.sh pausa brave wikidata",
             ("pausa", "brave", "wikidata") in sc.chiamate, sc.chiamate)
    st = mr.leggi()
    v = mr.vista()
    verifica("motore: in pausa nello stato, nella storia e nella vista",
             st.get("in_pausa") == ["brave", "wikidata"]
             and any(e.get("evento") == "motori" and "metto in pausa brave" in e.get("frase", "")
                     for e in st.get("storia") or [])
             and [x["motore"] for x in v["in_pausa"]] == ["brave", "wikidata"]
             and v["in_pausa"][0]["perche"] == "too many requests", (st.get("in_pausa"), v))
    n = len(sc.chiamate)
    mr.controlla("terminale")
    verifica("motore: pause invariate → lo script non si richiama",
             not any(c[0] == "pausa" for c in sc.chiamate[n:]), sc.chiamate[n:])
    # Pochi motori con qualcuno in pausa: degradata
    h.profili["http://127.0.0.1:8004"] = (8, ("duckduckgo",), ())
    r = mr.controlla("terminale")
    verifica("motore: pochi motori e qualcuno in pausa → degradata con il perché",
             r["stato"] == "degradata" and "in pausa brave, wikidata" in r["motivo"], r["motivo"])
    # Dopo i giorni si riprovano: lo script senza di loro
    orologio[0] += 4 * 86400
    h.profili["http://127.0.0.1:8004"] = (8, ("duckduckgo", "startpage", "qwant", "ansa"), ())
    n = len(sc.chiamate)
    r = mr.controlla("terminale")
    verifica("motore: dopo i giorni si riprovano (pausa senza motori), buona",
             ("pausa",) in sc.chiamate[n:] and mr.leggi().get("in_pausa") == []
             and r["stato"] == "buona", (sc.chiamate[n:], r["stato"]))
    # In automatico con Calliope ferma la pausa si applica; in uso no (la prossima volta)
    profilo = (8, ("duckduckgo", "startpage", "qwant"), (("brave", "too many requests"),))
    h2 = HttpFinto()
    h2.profili["http://127.0.0.1:8004"] = profilo
    sc2 = ScriptFinto()
    m2 = motore("pause-auto", h2, sc2, [], inattivita=lambda: 7200.0, lavori=lambda: 0,
                web_searxng_pausa_controlli=1)
    m2.controlla("automatico")
    verifica("automatico, ferma: pausa applicata", ("pausa", "brave") in sc2.chiamate,
             sc2.chiamate)
    h3 = HttpFinto()
    h3.profili["http://127.0.0.1:8004"] = profilo
    sc3 = ScriptFinto()
    m3 = motore("pause-occupata", h3, sc3, [], inattivita=lambda: 10.0, lavori=lambda: 0,
                web_searxng_pausa_controlli=1)
    m3.controlla("automatico")
    verifica("automatico, in uso: niente riavvio, la pausa resta da applicare",
             not any(c[0] == "pausa" for c in sc3.chiamate)
             and not m3.leggi().get("in_pausa"), sc3.chiamate)

    # Lo script non riesce: si torna alle pause di prima, errore nella storia
    class ScriptRotto(ScriptFinto):
        def __call__(self, *args, timeout=0):
            if args[0] == "pausa" and args[1:]:
                self.chiamate.append(args)
                return 1, "non risponde"
            return super().__call__(*args, timeout=timeout)
    h4 = HttpFinto()
    h4.profili["http://127.0.0.1:8004"] = profilo
    sc4 = ScriptRotto()
    m4 = motore("pause-rotto", h4, sc4, [], web_searxng_pausa_controlli=1)
    m4.controlla("terminale")
    verifica("script che non riesce: ritorno alle pause di prima ed errore nella storia",
             sc4.chiamate[-1] == ("pausa",) and not m4.leggi().get("in_pausa")
             and any(e.get("evento") == "errore" for e in m4.leggi().get("storia") or []),
             sc4.chiamate)
    # Dove SearXNG non si rifà (Windows, altra macchina): niente pause
    h5 = HttpFinto()
    h5.profili["http://127.0.0.1:8004"] = profilo
    sc5 = ScriptFinto()
    m5 = M.MotoreRicerca(cfg_di("pause-win", web_searxng_pausa_controlli=1), http=h5,
                         script=sc5, log=lambda x: None, controllabile=True, aggiornabile=False,
                         attendi=lambda s: None)
    m5.controlla("terminale")
    verifica("non aggiornabile: niente pause né script",
             not any(c[0] == "pausa" for c in sc5.chiamate)
             and not m5.leggi().get("in_pausa"), sc5.chiamate)


def prova_blocchi():
    h = HttpFinto()
    h.profili["http://127.0.0.1:8004"] = BUONO
    sc = ScriptFinto()
    m = motore("blocco", h, sc)
    entrato, esci = threading.Event(), threading.Event()
    vecchio = m._misura

    def lenta(url, img=""):
        entrato.set()
        esci.wait(5)
        return vecchio(url, img)
    m._misura = lenta
    t = threading.Thread(target=m.controlla)
    t.start()
    entrato.wait(5)
    try:
        m.controlla("terminale")
        verifica("due controlli insieme: il secondo no", False)
    except M.Occupato:
        verifica("due controlli insieme: il secondo no", True)
    esci.set()
    t.join(5)
    # Il blocco di un altro processo vivo
    m._misura = vecchio
    blocco = m._blocco()
    blocco.write_text(str(os.getppid() or 1))
    try:
        m.controlla("terminale")
        verifica("blocco di un altro processo: occupato", False)
    except M.Occupato:
        verifica("blocco di un altro processo: occupato", True)
    # Un blocco vecchio (processo caduto) non ferma per sempre
    vecchia = time.time() - M.BLOCCO_VECCHIO_S - 60
    os.utime(blocco, (vecchia, vecchia))
    r = m.controlla("terminale")
    verifica("blocco vecchio: si ignora", r["stato"] == "buona" and not blocco.exists(), r["stato"])


def prova_capacita():
    h = HttpFinto()
    h.profili["http://127.0.0.1:8004"] = SCARSO
    m = motore("capacita", h, ScriptFinto(), [])
    m.controlla()

    class WebFinto:
        diagnosi = {"codice": "ok"}
        motore = m
    cfg = cfg_di("capacita")
    d = capacita.check_web(cfg, WebFinto())
    verifica("capacità: «degradata» con motivo e passo", d["stato"] == "degradata"
             and "risultati" in d["motivo"] and "Aggiorna" in d["prossimo_passo"], d)
    reg = capacita.Registro()
    reg.da_dict(d)
    reg.segnala("casa", "attiva")
    verifica("riassunto: «va peggio»", "va peggio: ricerca web" in reg.riassunto(), reg.riassunto())
    aree = {a["chiave"]: a for a in capacita.aree(reg)}
    verifica("«cosa sai fare?»: la ricerca web degradata conta come funzionante",
             aree["ricerca"]["attiva"] and not aree["ricerca"]["mancano"], aree["ricerca"])
    from calliope.tools import stato as T

    class Ctx:
        pass
    frase = T._una(Ctx(), reg, "web", "amministra")
    verifica("a voce a chi amministra: funziona, ma peggio del solito",
             "peggio del solito" in frase and "Aggiorna" in frase, frase)
    frase = T._una(Ctx(), reg, "web", "familiare")
    verifica("a voce a un familiare: funziona", "non funziona" not in frase and "funziona" in frase, frase)
    # Buona: attiva
    h.profili["http://127.0.0.1:8004"] = BUONO
    m.controlla()
    verifica("dopo un controllo buono: attiva", capacita.check_web(cfg, WebFinto())["stato"] == "attiva")
    # SearXNG giù al controllo: la diagnosi del servizio diventa «giù» (guasta)
    h.profili.clear()
    w = WebFinto()
    w.diagnosi = {"codice": "ok"}
    m.web = w
    m.controlla()
    verifica("controllo senza risposta: capacità guasta", capacita.check_web(cfg, w)["stato"] == "guasta")


def prova_ambiente():
    cfg = Config()
    verifica("senza SearXNG: niente", M.ambiente(cfg)[:2] == (False, False))
    cfg.web_searxng_url = "http://127.0.0.1:8004"
    cfg.online = False
    verifica("senza rete: niente", M.ambiente(cfg)[:2] == (False, False))
    cfg.online = True
    cfg.web_searxng_url = "http://192.0.2.1:8004"
    c, a, perche = M.ambiente(cfg)
    verifica("SearXNG su un'altra macchina: controllo sì, aggiornamento no", c and not a
             and "altra macchina" in perche, perche)
    if not sys.platform.startswith("linux"):
        cfg.web_searxng_url = "http://127.0.0.1:8004"
        c, a, perche = M.ambiente(cfg)
        verifica("Windows: controllo sì, aggiornamento spento con il perché", c and not a and perche, perche)
        m = M.MotoreRicerca(cfg_di("win"), http=HttpFinto(), log=lambda x: None)
        verifica("Windows: aggiorna → spento", m.aggiorna()["esito"] == "spento")
        ok, frase = m.avvia_azione("aggiorna", "cruscotto:dario")
        verifica("Windows: il pulsante «Aggiorna» non parte", not ok and "non c'è" in frase, frase)
        verifica("Windows: la vista lo dice", m.vista()["aggiornabile"] is False and m.vista()["perche"])


# ─────────────────────────── cruscotto ───────────────────────────

def prova_cruscotto():
    import prova_cruscotto as PC
    from calliope.schermi import ArchivioSchermi, Schermi
    from calliope.schermi.cruscotto import Cruscotto
    from calliope.schermi.server import ServerSchermi
    shutil.rmtree(PC.TMP, ignore_errors=True)
    cfg = Config()
    d = TMP / "cruscotto"
    d.mkdir(parents=True, exist_ok=True)
    cfg.config_dir = str(d)
    cfg.memory_db = str(d / "memoria.db")
    cfg.turn_log_dir = str(d / "registro")
    cfg.estensioni_cartella = str(d / "estensioni")
    reg = PC.Registro(PC.Profilo("dario", "Dario", admin=True), PC.Profilo("bianca", "Bianca"))
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
    hub.server = srv
    cr = hub.cruscotto = Cruscotto(cfg, hub, servizi=PC.Servizi(reg),
                                   registro_capacita=capacita.Registro())
    try:
        arch = hub.archivio
        _, t_admin = arch.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario")
        _, t_fam = arch.crea_con_token("camera", proprietario="bianca", proprietario_nome="Bianca")
        _, t_stanza = arch.crea_con_token("cucina")
        hub._rinfresca()
        port = srv.port
        verifica("cruscotto senza motore: nessuna sezione «motore»", "motore" not in cr.dati(True))
        st, r = PC.chiedi(port, "/api/motore", PC.chiedi(port, "/api/accedi", token=t_admin,
                                                         metodo="POST")[1]["sessione"], metodo="POST")
        verifica("/api/motore senza motore → 404", st == 404, (st, r))

        h = HttpFinto(_registro_hub(time.time()))
        h.profili["http://127.0.0.1:8004"] = BUONO
        sc = ScriptFinto(in_uso=NUOVA)
        m = motore("cruscotto", h, sc)
        cr.motore = m
        m.avvisa = cr.avvisa
        dati = cr.dati()
        verifica("cruscotto con motore: sezione con modo, immagine, giudizio",
                 dati.get("motore", {}).get("modo") == "automatico"
                 and dati["motore"]["giudizio"]["stato"] == "mai")

        def sessione(tok):
            return PC.chiedi(port, "/api/accedi", token=tok, metodo="POST")[1]["sessione"]

        def post(sess, corpo):
            import urllib.request, urllib.error
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/motore", method="POST",
                                         data=json.dumps(corpo).encode(),
                                         headers={"X-Calliope-Sessione": sess,
                                                  "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=20) as x:
                    return x.status, json.loads(x.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")
        s_admin, s_fam, s_stanza = sessione(t_admin), sessione(t_fam), sessione(t_stanza)
        for nome, s in (("familiare", s_fam), ("di stanza", s_stanza)):
            st, r = post(s, {"azione": "controlla"})
            verifica(f"/api/motore da uno schermo {nome} → 403", st == 403, (st, r))
        st, r = post("falsa", {"azione": "controlla"})
        verifica("/api/motore senza sessione valida → 401", st == 401, st)
        st, r = post(s_admin, {"azione": "cancella"})
        verifica("/api/motore: azione sconosciuta → 400", st == 400, (st, r))
        st, r = post(s_admin, {"azione": "controlla", "gettone": "inventato"})
        verifica("/api/motore: gettone inventato → rifiutato", st == 409 and "scaduta" in r["frase"], (st, r))
        st, g = post(s_admin, {"azione": "controlla"})
        verifica("primo tocco: un gettone", st == 200 and g.get("gettone") and g.get("scade_s") == 60, (st, g))
        st, r = post(s_admin, {"azione": "aggiorna", "gettone": g["gettone"]})
        verifica("gettone di «controlla» non vale per «aggiorna»", st == 409, (st, r))
        st, g = post(s_admin, {"azione": "controlla"})
        # Lo stesso gettone da un altro schermo (di chi amministra, ma un altro)
        schermo_admin = next(x for x in hub.abbinati() if x.get("proprietario") == "dario")
        altro = {**schermo_admin, "id": schermo_admin["id"] + 999}
        ok, frase = cr.esegui(altro, "controlla", g["gettone"])
        verifica("gettone di un altro schermo: rifiutato (e consumato)", not ok, frase)
        st, g = post(s_admin, {"azione": "controlla"})
        st, r = post(s_admin, {"azione": "controlla", "gettone": g["gettone"]})
        verifica("secondo tocco: il controllo parte", st == 200 and r.get("ok"), (st, r))
        for _ in range(100):
            if m.in_corso is None:
                break
            time.sleep(0.05)
        v = cr.dati()["motore"]
        verifica("il cruscotto mostra l'esito del controllo (sempre fresco, senza cache)",
                 v["giudizio"]["stato"] == "buona" and v["storia"][0]["chi"] == "cruscotto:dario", v["giudizio"])
        cr._richieste.clear()            # il limite al minuto si prova dopo
        st, r = post(s_admin, {"azione": "controlla", "gettone": g["gettone"]})
        verifica("lo stesso gettone una seconda volta: rifiutato", st == 409
                 and "scaduta" in r["frase"], (st, r))
        # Scaduto
        st, g = post(s_admin, {"azione": "controlla"})
        cr._gettoni[g["gettone"]]["scade"] = time.monotonic() - 1
        st, r = post(s_admin, {"azione": "controlla", "gettone": g["gettone"]})
        verifica("gettone scaduto: rifiutato", st == 409 and "scaduta" in r["frase"], (st, r))
        # Limite al minuto
        cr._richieste.clear()
        codici = [post(s_admin, {"azione": "controlla"})[0] for _ in range(8)]
        verifica("al più AZIONI_MINUTO richieste al minuto per schermo", 429 in codici, codici)
        # Avviso: solo agli schermi personali di chi amministra
        ricevuti = []
        vero = hub.invia_a
        hub.invia_a = lambda sid, scheda: (ricevuti.append((sid, scheda)), vero(sid, scheda))[1] or True
        n = cr.avvisa("SearXNG", "Ho aggiornato SearXNG")
        sids = {x[0] for x in ricevuti}
        verifica("avviso: solo lo schermo personale di chi amministra", n == 1
                 and sids == {schermo_admin["id"]} and ricevuti[0][1]["visibilita"] == "personale",
                 (n, sids))
    finally:
        srv.ferma()
        hub.archivio.close()


# ─────────────────────────── lo script con docker finto ───────────────────────────

def _bash() -> str | None:
    if os.name == "nt":
        for p in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"):
            if Path(p).is_file():
                return p
        return None                      # niente bash di WSL: non è quello di Git
    return shutil.which("bash")


DOCKER_FINTO = """#!/usr/bin/env bash
echo "$*" >> "$REGISTRO_FINTO"
case "$1" in
  image) [ "$2" = rm ] && exit 0 ;;
  pull) exit 0 ;;
  run) exit 0 ;;
  rm) exit 0 ;;
esac
exit 0
"""
CURL_FINTO = """#!/usr/bin/env bash
exit 0
"""


def prova_script():
    bash = _bash()
    if bash is None:
        print("SALTATA IN PARTE: nessun bash di Git, lo script con docker finto non si prova")
        return
    script = Path(__file__).resolve().parents[1] / "setup" / "linux" / "motore" / "searxng.sh"
    bindir = TMP / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    for nome, testo in (("docker", DOCKER_FINTO), ("curl", CURL_FINTO)):
        f = bindir / nome
        f.write_text(testo, encoding="utf-8", newline="\n")
        f.chmod(0o755)
    cartella = TMP / "motore-searxng"
    registro = TMP / "docker.log"

    def corri(*args, **env):
        e = {**os.environ, "DIR": cartella.as_posix(), "PORTA": "8004",
             "REGISTRO_FINTO": registro.as_posix(), "HOME": TMP.as_posix()}
        e.pop("IMMAGINE", None)
        e.update(env)
        # PATH con i finti davanti, dentro bash (su Windows i percorsi vanno convertiti)
        pre = subprocess.run([bash, "-c", f"cygpath -u '{bindir}' 2>/dev/null || echo '{bindir.as_posix()}'"],
                             capture_output=True, text=True).stdout.strip()
        cmd = f'export PATH="{pre}:$PATH"; exec bash "$0" "$@"'
        r = subprocess.run([bash, "-c", cmd, script.as_posix(), *args], capture_output=True,
                           text=True, env=e, timeout=60)
        return r.returncode, (r.stdout + r.stderr).strip()

    def comandi():
        try:
            righe = registro.read_text(encoding="utf-8").splitlines()
        except OSError:
            righe = []
        registro.write_text("", encoding="utf-8")
        return righe

    testo = script.read_text(encoding="utf-8")
    fissata = testo.split('FISSATA="', 1)[1].split('"', 1)[0]
    rc, out = corri("immagine")
    verifica("script: immagine fissata senza scelta", rc == 0 and out == fissata, out)
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / "immagine").write_text(NUOVA + "\n", encoding="utf-8")
    rc, out = corri("immagine")
    verifica("script: l'immagine scelta più recente vince", out == NUOVA, out)
    vecchia = f"searxng/searxng:2026.9.1-abcdef1@{DIG[3]}"
    (cartella / "immagine").write_text(vecchia + "\n", encoding="utf-8")
    rc, out = corri("immagine")
    verifica("script: una scelta più vecchia della fissata no", out == fissata, out)
    (cartella / "immagine").write_text("searxng/searxng:latest\n", encoding="utf-8")
    rc, out = corri("immagine")
    verifica("script: una scelta non valida no", out == fissata, out)
    comandi()
    for cattiva in ("searxng/searxng:latest", f"altro/searxng:2026.10.7-6671d89be@{DIG[2]}",
                    "searxng/searxng:2026.10.7-6671d89be", f"{NUOVA}; rm -rf /"):
        rc, out = corri("usa", cattiva)
        verifica(f"script: «usa» rifiuta {cattiva[:40]}", rc == 2, (rc, out))
        rc, out = corri("candidata", cattiva)
        verifica(f"script: «candidata» rifiuta {cattiva[:40]}", rc == 2, (rc, out))
    verifica("script: nessun comando docker per le immagini rifiutate", not comandi())
    rc, out = corri("candidata", NUOVA)
    cmd = comandi()
    run = next((c for c in cmd if c.startswith("run ")), "")
    verifica("script: candidata scaricata e avviata sulla porta di prova, senza riavvio",
             rc == 0 and out.endswith("http://127.0.0.1:10004") and f"pull -q {NUOVA}" in cmd
             and "127.0.0.1:10004:8080" in run and "calliope-searxng-candidata" in run
             and "--restart" not in run and run.endswith(NUOVA) and "--read-only" in run
             and "--log-driver none" in run, (rc, out, cmd))
    verifica("script: candidata nella lista delle scaricate",
             (cartella / "scaricate").read_text(encoding="utf-8").split() == [NUOVA])
    rc, out = corri("usa", NUOVA)
    cmd = comandi()
    run = next((c for c in cmd if c.startswith("run ")), "")
    verifica("script: «usa» sceglie l'immagine e rifà il container vero",
             rc == 0 and (cartella / "immagine").read_text(encoding="utf-8").strip() == NUOVA
             and "--name calliope-searxng --restart unless-stopped" in run
             and "127.0.0.1:8004:8080" in run and run.endswith(NUOVA), (rc, out, run))
    # Pulizia: solo le scaricate da qui, mai quella in uso né quelle tenute
    altra = f"searxng/searxng:2026.10.4-d48c4b555@{DIG[6]}"
    (cartella / "scaricate").write_text("\n".join([VECCHIA, altra, NUOVA]) + "\n",
                                        encoding="utf-8", newline="\n")
    rc, out = corri("pulisci-immagini", VECCHIA)
    cmd = comandi()
    tolte = [c for c in cmd if c.startswith("image rm")]
    verifica("script: pulizia solo delle scaricate non tenute né in uso, senza -f",
             tolte == [f"image rm {altra}"], tolte)
    verifica("script: la lista resta con quelle tenute",
             sorted((cartella / "scaricate").read_text(encoding="utf-8").split()) == sorted([VECCHIA, NUOVA]))
    rc, out = corri("dimentica")
    rc, out = corri("immagine")
    verifica("script: «dimentica» torna alla fissata", out == fissata, out)
    # Motori in pausa e tempi massimi (09/10 sera)
    comandi()
    rc, out = corri("pausa", "brave", "wikidata")
    impost = (cartella / "settings.yml").read_text(encoding="utf-8")
    keep = impost.split("keep_only:", 1)[1].split("general:", 1)[0]
    cmd = comandi()
    verifica("script: «pausa» scrive i motori e rifà il container",
             rc == 0 and (cartella / "in-pausa").read_text(encoding="utf-8").split()
             == ["brave", "wikidata"] and "In pausa: brave, wikidata" in out
             and any(c.startswith("run ") and "--name calliope-searxng " in c for c in cmd),
             (rc, out, cmd))
    verifica("script: le impostazioni senza i motori in pausa",
             '"brave"' not in keep and '"wikidata"' not in keep and '"duckduckgo"' in keep
             and '"ansa"' in keep, keep)
    verifica("script: timeout 2 s ai generali, 3 s alle notizie, ANSA accesa",
             "request_timeout: 2.0" in impost
             and '- name: "ansa"\n    timeout: 3.0\n    disabled: false' in impost
             and '- name: "bing news"\n    timeout: 3.0' in impost,
             impost.split("outgoing:", 1)[1])
    rc, out = corri("pausa", "ansa")
    impost = (cartella / "settings.yml").read_text(encoding="utf-8")
    verifica("script: un motore delle notizie in pausa sparisce anche dalle sue impostazioni",
             '"ansa"' not in impost.split("general:", 1)[0] and 'name: "ansa"' not in impost,
             impost)
    rc, out = corri("pausa", "brave; rm -rf /")
    verifica("script: «pausa» rifiuta un motore sconosciuto, il file resta",
             rc == 2 and (cartella / "in-pausa").read_text(encoding="utf-8").split() == ["ansa"],
             (rc, out))
    rc, out = corri("pausa")
    impost = (cartella / "settings.yml").read_text(encoding="utf-8")
    verifica("script: «pausa» senza motori toglie tutte le pause",
             rc == 0 and not (cartella / "in-pausa").read_text(encoding="utf-8").strip()
             and '"brave"' in impost and 'name: "ansa"' in impost, (rc, out))
    comandi()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        prova_giudizio()
        prova_registro()
        prova_aggiornamento()
        prova_automatico()
        prova_pause()
        prova_blocchi()
        prova_capacita()
        prova_ambiente()
        prova_cruscotto()
        prova_script()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
