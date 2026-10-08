"""La scheda dello sviluppo e del lavoro in diretta, a secco (08/10/2026, richieste di Dario
dopo il giro vero della DGX delle 14:36–15:30: calliope/agenti/avanzamento.py,
calliope/sviluppo.py, calliope/schermi/hub.py e scarica.py). Nomi di fantasia, numeri veri.

1. I conti dei token: il caso vero («Meteo città», S1: il primo lavoro, due correzioni (L2, L3,
   con una tappa alla fine del giro 1 di L3), poi due ritorni all'analisi con un lavoro nuovo
   ciascuno (L4, L6); L1 10 570, L2 6 191, L3 92 957 in
   due giri, L4 24 310, L6 21 680 token generati): ogni lavoro conta i suoi, lo sviluppo la
   somma (155 708); la correzione N si riconosce («riparte dalla versione provata»); il lavoro
   in corso con i numeri di adesso; un id che si ripete dopo un riavvio è un altro lavoro.
2. I tetti per giro: al giro 2 passate 48, minuti 60, token il doppio, e il tempo continua a
   contare oltre i 30 minuti (prima restava «di 30 min»).
3. La vista: i dati strutturati della scheda `sviluppo:<id>` (fasi, versione, giro, tappa,
   collaudi, domande, revisione, numeri), il Markdown di prima resta.
4. Gli schermi: a ogni fase la scheda va agli schermi personali di chi sviluppa (computer e
   telefono), mai a quelli della stanza né a quelli di un'altra persona; chiusa o sospesa, ci
   arriva con lo stato (la pagina esce dalla vista).
5. La cronologia degli schermi: la scheda in diretta va alle pagine con i pezzi nuovi, nella
   cronologia con la finestra intera (`_storia`); «Scarica il registro» solo dallo schermo
   personale di chi l'ha chiesto, con il file del registro letto al clic.

    python prove\\prova_scheda_sviluppo.py
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from calliope.agenti.avanzamento import Avanzamento, _Segue  # noqa: E402
from calliope.agenti.ciclo import Lavoro  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.schermi import schede  # noqa: E402
from calliope.schermi.archivio import ArchivioSchermi  # noqa: E402
from calliope.schermi.hub import Mittente, Schermi, pubblica  # noqa: E402
from calliope.sviluppo import Sviluppi  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok else ""),
          flush=True)


def lavoro(ident, token, passi, secondi, creato, correzione=False, giro=1, stato="fatto",
           attesa=0.0):
    lav = Lavoro(ident, "estensione", "meteo per città", "dario-id", "Dario",
                 titolo="Meteo città")
    lav.creato = creato
    lav.inizio = creato + 5
    lav.fine = None if stato == "in_corso" else lav.inizio + secondi + attesa
    lav.attesa_s = attesa
    lav.token, lav.passi, lav.stato, lav.giro = token, passi, stato, giro
    lav.ragionamento = token // 3
    if correzione:
        lav.correzione = True
    return lav


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="calliope-scheda-sviluppo-"))
    cfg = Config()
    lavori = SimpleNamespace(lavori=[])
    svs = Sviluppi(cfg, tmp, lavori=lavori, log=lambda m: None)

    # ── 4 (prima): gli schermi ──
    arch = ArchivioSchermi(str(tmp / "schermi.db"))
    hub = Schermi(cfg, arch, log=lambda m: None)
    studio, _ = arch.crea_con_token("studio", "dario-id", "Dario")
    telefono, _ = arch.crea_con_token("telefono-dario", "dario-id", "Dario")
    cucina, _ = arch.crea_con_token("cucina")
    camera, _ = arch.crea_con_token("camera", "bianca-id", "Bianca")
    hub._rinfresca()
    svs.schermi = hub

    # ── 1. i conti dei token, sul giro vero ──
    print("── conti dei token (giro vero dell'08/10, nomi di fantasia) ──")
    t0 = time.time() - 3600
    sv = svs.apri("dario-id", "Dario", "estensione", "Crea un'estensione che mi dica il meteo "
                                                      "di una città", "meteo città")
    storia_studio = [c for c in hub.storia(studio["id"]) if c.get("chiave") == f"sviluppo:{sv.id}"]
    verifica("aperto: la scheda va subito agli schermi personali di chi sviluppa",
             storia_studio and storia_studio[-1]["tipo"] == "sviluppo"
             and storia_studio[-1]["sviluppo"]["stato"] == "aperta"
             and any(c.get("chiave") == f"sviluppo:{sv.id}" for c in hub.storia(telefono["id"])))
    verifica("…mai a quelli della stanza né a quelli di un'altra persona",
             not any(c.get("tipo") == "sviluppo" for c in hub.storia(cucina["id"]))
             and not any(c.get("tipo") == "sviluppo" for c in hub.storia(camera["id"])))
    numeri = [("L1", 10570, 13, 179.9, False, 1), ("L2", 6191, 8, 100.9, True, 1),
              ("L3", 92957, 33, 1521.6, True, 2), ("L4", 24310, 14, 368.0, False, 1),
              ("L6", 21680, 12, 317.5, False, 1)]
    for i, (ident, tok, passi, sec, corr, giro) in enumerate(numeri):
        lav = lavoro(ident, tok, passi, sec, t0 + i * 600, correzione=corr, giro=giro,
                     stato="in_corso")
        lavori.lavori.append(lav)
        if corr:
            sv.correzioni += 1
        if sv.fase != "sviluppo":
            svs.passa(sv, "sviluppo", "correzione")      # come sviluppo_correggi
        svs.avviato(lav)
        r = svs.riepilogo_lavoro(lav)
        if ident == "L2":
            verifica("la prima correzione: «correzione 1» sulla scheda del lavoro",
                     r and r["correzione"] == 1 and r["fase"] == "sviluppo", str(r))
        if ident == "L1":
            verifica("il primo lavoro non è una correzione, e lo sviluppo conta i suoi token",
                     r and r["correzione"] == 0 and r["totali"]["token"] == 10570
                     and r["fase_nome"] == "sviluppo e test" and r["n_fase"] == 2, str(r))
        lav.stato, lav.fine = "fatto", lav.inizio + sec
        svs.lavoro_finito(lav, {"messaggio": "fatto"})
    tot = svs.totali(sv)
    verifica("lo sviluppo intero: la somma dei lavori (155 708 token, 80 passate, 5 lavori)",
             tot["token"] == 155708 and tot["passate"] == 80 and tot["lavori"] == 5
             and tot["correzioni"] == 2, json.dumps(tot))
    verifica("…e sulla scheda in Markdown",
             "155 708 token generati in tutto" in svs.testo_scheda(sv),
             svs.testo_scheda(sv)[-300:])
    # Un lavoro in corso: i suoi numeri di adesso entrano nel totale
    sv.correzioni += 1
    svs.passa(sv, "sviluppo", "correzione")
    vivo = lavoro("L7", 1000, 2, 60, time.time() - 70, correzione=True, stato="in_corso")
    lavori.lavori.append(vivo)
    svs.avviato(vivo)
    vivo.token, vivo.passi = 4000, 5
    r = svs.riepilogo_lavoro(vivo)
    verifica("il lavoro in corso: correzione 3, e il totale con i suoi numeri di adesso",
             r["correzione"] == 3 and r["totali"]["token"] == 155708 + 4000
             and r["totali"]["lavori"] == 6, json.dumps(r))
    # Dopo un riavvio gli id ripartono: un altro «L1» è un altro lavoro
    nuovo_l1 = lavoro("L1", 500, 1, 20, time.time() + 5, stato="in_corso")
    lavori.lavori.append(nuovo_l1)
    vivo.stato = "fatto"
    svs.lavoro_finito(vivo, {"messaggio": "fatto"})
    sv.fase = "sviluppo"
    svs.avviato(nuovo_l1)
    verifica("un id che si ripete dopo un riavvio è un altro lavoro (non sostituisce il primo)",
             svs.totali(sv)["lavori"] == 7 and svs.totali(sv)["token"] == 155708 + 4000 + 500,
             json.dumps(svs.totali(sv)))
    verifica("un lavoro che non è di uno sviluppo: niente riepilogo",
             svs.riepilogo_lavoro(lavoro("L99", 1, 1, 1, time.time())) is None)
    # Riletti dal disco
    dopo = Sviluppi(cfg, tmp, lavori=SimpleNamespace(lavori=[]), log=lambda m: None)
    sv2 = next(s for s in dopo.sviluppi if s.id == sv.id)
    verifica("i lavori dello sviluppo restano su disco (riavvio)",
             len(sv2.lavori) == 7 and dopo.totali(sv2)["token"] == 155708 + 4000 + 500)

    # ── 2. i tetti per giro ──
    print("── tetti per giro ──")
    av = Avanzamento(lambda lav=None: (24, 150000, 1800), sviluppo=svs.riepilogo_lavoro,
                     log=lambda m: None)
    l3 = lavoro("L3", 70000, 26, 0, time.time() - 2400, giro=2, stato="in_corso", attesa=300)
    l3.fine = None
    ist = av._istantanea(_Segue(l3), False)
    verifica("giro 2: passate 48, minuti 60, token 300 000 (cumulativi)",
             ist["giro"] == 2 and ist["max_passate"] == 48 and ist["max_s"] == 3600
             and ist["max_token"] == 300000, json.dumps({k: ist[k] for k in (
                 "giro", "max_passate", "max_s", "max_token")}))
    verifica("il tempo continua a contare oltre i 30 minuti (l'attesa non conta)",
             1990 < ist["trascorso_s"] < 2110 and ist["dal"], ist["trascorso_s"])
    l1 = lavoro("L8", 10, 1, 0, time.time() - 60, stato="in_corso")
    ist1 = av._istantanea(_Segue(l1), False)
    verifica("giro 1: i tetti di un giro", ist1["max_passate"] == 24 and ist1["max_s"] == 1800
             and ist1["max_token"] == 150000)

    # ── 3. la vista ──
    print("── la vista dello sviluppo ──")
    sv.fase, sv.versione, sv.estensione = "collaudo", 3, "meteo_citta"
    svs.collaudo(sv, "Bergamo", True, "A Bergamo ci sono 18 gradi.")
    svs.collaudo(sv, "Valfiorita Maggiore", False, "Impossibile cercare la città")
    svs.chiesto(sv, "Perché Valfiorita Maggiore non va?", {
        "voce": "Il geocoder non trova i nomi di due parole.",
        "dettagli": "In estensione.py la ricerca usa solo la prima parola.",
        "serve_correzione": True})
    l9 = lavoro("L9", 100, 2, 0, time.time() - 30, stato="in_attesa", giro=2)
    l9.risultato = {"esito": "tappa"}
    lavori.lavori.append(l9)
    sv.lavoro = "L9"
    card = svs.scheda(sv)
    v = card["sviluppo"]
    verifica("la scheda: tipo «sviluppo», chiave sviluppo:<id>, il Markdown di prima resta",
             card["tipo"] == "sviluppo" and card["chiave"] == f"sviluppo:{sv.id}"
             and "**adesso: collaudo**" in card["markdown"] and card.get("scarica"))
    verifica("fasi: fatte, adesso, mancano",
             [f["stato"] for f in v["fasi"]] == ["fatta", "fatta", "adesso", "manca", "manca"]
             and v["fasi"][2]["nome"] == "collaudo", str(v["fasi"]))
    verifica("nome, versione, giro, tappa, correzioni, lavoro",
             v["nome"] == "meteo_citta" and v["versione"] == 3 and v["giro"] == 2
             and v["tappa"] is True and v["correzioni"] == 3 and v["lavoro"] == "lavoro:L9",
             json.dumps({k: v[k] for k in ("nome", "versione", "giro", "tappa", "correzioni",
                                           "lavoro")}))
    verifica("collaudi (dati, esito, versione) e domande a chi l'ha scritto",
             [c["dati"] for c in v["collaudi"]] == ["Bergamo", "Valfiorita Maggiore"]
             and v["collaudi"][1]["ok"] is False and v["collaudi"][1]["versione"] == 3
             and v["chiesti"][0]["dettagli"].startswith("In estensione.py"))
    verifica("i numeri dello sviluppo nella vista", v["totali"]["lavori"] == 7, str(v["totali"]))
    pub = json.dumps(pubblica(card), ensure_ascii=False)
    verifica("niente della sorgente sul server nella scheda pubblica", "_scarica" not in pub)

    # ── 4. chiusa e sospesa: la scheda ci arriva con lo stato ──
    print("── uscita dalla vista ──")
    svs.sospendi(sv, "chiesto")
    ult = [c for c in hub.storia(studio["id"]) if c.get("chiave") == f"sviluppo:{sv.id}"][-1]
    verifica("sospeso: la scheda arriva con lo stato «sospesa»",
             ult["sviluppo"]["stato"] == "sospesa")
    svs.riprendi(sv)
    svs.chiudi(sv, "uscita")
    ult = [c for c in hub.storia(telefono["id"]) if c.get("chiave") == f"sviluppo:{sv.id}"][-1]
    verifica("chiuso: anche sul telefono, con lo stato «chiusa»",
             ult["sviluppo"]["stato"] == "chiusa" and len(
                 [c for c in hub.storia(telefono["id"]) if c.get("chiave") == f"sviluppo:{sv.id}"]) == 1)
    verifica("e ancora niente sugli schermi degli altri",
             not any(c.get("tipo") == "sviluppo" for c in hub.storia(cucina["id"])
                     + hub.storia(camera["id"])))

    # ── 5. la cronologia degli schermi e «Scarica il registro» ──
    print("── cronologia e registro ──")
    reg_file = tmp / "lavoro-L5" / ".registro-agente.md"
    reg_file.parent.mkdir(parents=True)
    reg_file.write_text("# Registro\n\n## passata 1\n\n→ scrivi_file · a.py\n", encoding="utf-8")
    finestra = {"id": "x", "fino": 3, "finestra": True, "taglio": False,
                "pezzi": [{"n": i, "s": i, "t": "testo", "x": f"pezzo {i}"} for i in (1, 2, 3)]}
    vivo_av = {"flusso": {"id": "x", "fino": 3, "pezzi": [{"n": 3, "s": 3, "t": "testo",
                                                          "x": "pezzo 3"}]}}
    c = schede.lavoro_avanzamento("Meteo città", "estensione", "in_corso", vivo_av, ident="L5")
    c["_storia"] = {"avanzamento": {**c["avanzamento"], "flusso": finestra}}
    c["registro"] = {"chiave": "registro:L5", "formati": ["md"]}
    c["_registro"] = {"markdown_file": str(reg_file), "titolo": "Registro di Meteo città"}
    dario = Mittente("dario-id", "Dario", "amministra", True)
    esito = hub.invia(c, dario)
    st = [x for x in hub.storia(studio["id"]) if x.get("chiave") == "lavoro:L5"][-1]
    verifica("alle pagine i pezzi nuovi, nella cronologia la finestra intera",
             [p["n"] for p in pubblica(c)["avanzamento"]["flusso"]["pezzi"]] == [3]
             and [p["n"] for p in st["avanzamento"]["flusso"]["pezzi"]] == [1, 2, 3]
             and st["avanzamento"]["flusso"]["finestra"] is True
             and "_storia" not in st and "_registro" not in st, str(esito))
    voce = hub.scaricamenti.voce(studio["id"], "registro:L5")
    verifica("«Scarica il registro» registrato per gli schermi personali di chi l'ha chiesto",
             voce is not None and hub.scaricamenti.voce(cucina["id"], "registro:L5") is None)
    g = hub.scaricamenti.gettone(studio, "registro:L5", "md")
    nome, tipo, dati = hub.scaricamenti.prendi(g["url"].rsplit("/", 1)[-1])
    verifica("il registro si scarica in Markdown, letto dal file al clic",
             tipo.startswith("text/markdown") and b"scrivi_file" in dati and nome.endswith(".md"),
             f"{nome} {tipo}")
    try:
        hub.scaricamenti.gettone(camera, "registro:L5", "md")
        altro = False
    except Exception:  # noqa: BLE001
        altro = True
    verifica("…e non da uno schermo di un'altra persona", altro)
    grigio = Mittente("dario-id", "Dario", "familiare", False)
    c2 = dict(c, chiave="lavoro:L55", registro={"chiave": "registro:L55", "formati": ["md"]})
    hub.invia(c2, grigio)
    verifica("zona grigia: niente scheda e niente registro scaricabile",
             hub.scaricamenti.voce(studio["id"], "registro:L55") is None)

    arch.close()
    print("\nTutto a posto." if not errori else f"\n{errori} errori.")
    return 1 if errori else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
