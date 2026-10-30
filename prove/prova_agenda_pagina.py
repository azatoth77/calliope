"""Prova a secco della pagina Agenda, dei tasti del timer e del vincolo dei tocchi (28/10/2026,
passo 2b di docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md, issue #257 e #262 di #241;
aree docs/aree/schermi-telefono.md, sicurezza-politica.md e memoria-agenda-liste.md).

1. **Il vincolo dei tocchi** (`schermi/tocchi.py`, #262 e #266): passano solo i `TOCCABILI`,
   ognuno col suo perché; gli `ESCLUSI` (dimentica, catture, rubrica, richiesta al tutore,
   risposta all'agente, ciò che vuole la voce) rifiutati col motivo; un'«azione» con una fonte non
   fidata e un tool solo per chi amministra no; come difesa in più, un
   tool pericoloso, senza classe, che legge dati non fidati, irreversibile, con un effetto oltre
   E2 o declassato dal suo `ToolSpec` no; un tocco nuovo su un tool non ammesso ferma l'import
   del modulo (l'avvio); `prepara` rifiuta un tocco che chiama un altro tool (403); il ciclo
   rifiuta un tool non ammesso o diverso da quello del tocco senza chiamarlo
   (`tocco_non_ammesso`), e azzera per il tocco la proposta in sospeso, il «sì» già dato e il
   gioco del turno di prima, rimettendoli dopo.
2. **La vista per giorno** (`agenda.per_giorno`): i bordi di mezzanotte, il sesto e il settimo
   giorno, gli avvisi interni e le voci già scadute fuori, i timer a parte; le schede del giorno
   (`schede.giorno`) e la pagina (`raccolte.pagina(…, "agenda")`) con l'Agenda vera: i timer di
   casa con chi li ha messi, solo i promemoria della persona.
3. **I tasti del timer** (`tocchi.prepara`): chiave non valida 400, senza agenda 503, timer che
   non c'è, suonato, con l'id riusato o che non è un timer 409; «+1 minuto» → `timer_imposta`
   «aggiungi», «Ferma» → `agenda_annulla`, con il bersaglio.
4. **Il ciclo** con un `ToolRegistry` vero e l'`Agenda` su disco: «+1 minuto» e «Ferma» cambiano
   il timer toccato e non l'ultimo messo (due timer senza nome), registro dei turni, storia che
   chiude con Calliope, la scheda aggiornata allo schermo del tocco, l'evento «tocco»; il timer
   suonato nel frattempo: rifiuto con il motivo e nessun timer nuovo; ogni escluso e un tool
   fuori dall'elenco rifiutati senza chiamarli (#266). Con l'hub vero e due stanze (#266): lo
   schermo senza stanza manda il timer alla stanza predefinita, senza quella a tutti, con la sua
   stanza a quella; il mittente col livello vero limitato come lo scritto; `conv_archivio` della
   conversazione del tocco.
5. **Il server** vero su 127.0.0.1: la pagina Agenda da `/api/raccolte`, il tocco del timer
   nell'ingresso con il bersaglio e la chiave, 409 per un timer che non c'è, oltre 30 tocchi 429.

Nomi e dati di fantasia, niente rete né modelli.

    python prove/prova_agenda_pagina.py
"""

import dataclasses
import datetime
import json
import os
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from calliope import politica, valore  # noqa: E402
from calliope.agenda import Agenda, per_giorno  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.schermi import ArchivioSchermi, Schermi  # noqa: E402
from calliope.schermi import raccolte, schede, tocchi  # noqa: E402
from calliope.schermi.server import ServerSchermi  # noqa: E402
from calliope.tools.spec import ToolContext, ToolSpec  # noqa: E402

import prova_raccolte as pr  # noqa: E402  (i finti del 2a: persone, hub, ciclo)

TMP = Path(tempfile.mkdtemp(prefix="calliope-agenda-pagina-"))
pr.TMP = TMP
ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({dettaglio})" if dettaglio and not ok else ""),
          flush=True)
    if not ok:
        ERRORI.append(nome)


ORIGINALI = tocchi.TOCCHI


def metti_tocco(nome, t):
    """Un tocco di prova: `TOCCHI` è immutabile (#266), si rimpiazza tutto il dizionario."""
    tocchi.TOCCHI = types.MappingProxyType({**dict(tocchi.TOCCHI), nome: t})


def rimetti_tocchi():
    tocchi.TOCCHI = ORIGINALI


def agenda_nuova(nome):
    return Agenda(str(TMP / f"{nome}.db"))


# ─────────────────────────── 1. il vincolo dei tocchi ───────────────────────────
def vincolo():
    # Immutabili a runtime (#266, revisione della PR #270)
    for nome, m in (("TOCCHI", ORIGINALI), ("TOCCABILI", tocchi.TOCCABILI), ("ESCLUSI", tocchi.ESCLUSI)):
        try:
            m["prova"] = None
            fermo = False
        except TypeError:
            fermo = True
        verifica(f"vincolo: {nome} non si cambia a runtime", fermo and "prova" not in m)
    verifica("vincolo: i tocchi dell'elenco sono ammessi (anche all'import)",
             tocchi.controlla() == [] and tocchi._ERRORI == []
             and {t.tool for t in tocchi.TOCCHI.values()} == {"lista_togli", "timer_imposta", "agenda_annulla",
                                                              "studio"})
    verifica("vincolo: «Ferma» (agenda_annulla) è azione ed E2, quindi ammesso",
             politica.classe_di("agenda_annulla").classe == politica.AZIONE
             and valore.effetto("agenda_annulla", {}) == valore.E2
             and tocchi.ammesso("agenda_annulla", {"cosa": "il timer di 5 minuti"}) is None)
    # L'elenco in positivo (#266): solo i toccabili, ognuno con la sua riga
    ammessi = sorted(n for n in politica.CLASSI if tocchi.ammesso(n) is None)
    verifica("vincolo: fra i tool della politica passano solo i toccabili (prima 46 su 80)",
             ammessi == sorted(tocchi.TOCCABILI) == ["agenda_annulla", "lista_togli", "studio", "timer_imposta"],
             str(ammessi))
    verifica("vincolo: ogni toccabile ha la riga che dice perché, e i tasti del timer vogliono il bersaglio",
             all(len(t.perche) > 40 for t in tocchi.TOCCABILI.values())
             and tocchi.TOCCABILI["timer_imposta"].bersaglio and tocchi.TOCCABILI["agenda_annulla"].bersaglio
             and not tocchi.TOCCABILI["lista_togli"].bersaglio)
    larghi = [n for n in politica.CLASSI if tocchi._condizioni(n) is None and n not in tocchi.TOCCABILI]
    verifica("vincolo: i tool che le sole condizioni ammetterebbero sono fuori dall'elenco",
             len(larghi) >= 40 and all("toccabili" in (tocchi.ammesso(n) or "") or "escluso" in (tocchi.ammesso(n) or "")
                                       for n in larghi), str(len(larghi)))
    # Gli esclusi in modo esplicito: le condizioni da sole ne lascerebbero passare molti
    obbligati = ("dimentica", "pc_guarda", "anagrafica_salva", "anagrafica_cerca", "richiesta_tutore",
                 "lavoro_rispondi", "registra_utente", "cambia_voce", "installa_proponi", "modello_compila",
                 "sviluppo_apri", "conoscenti", "conoscente_livello", "minore_gestisci")
    for tool in obbligati:
        m = tocchi.ammesso(tool) or ""
        verifica(f"vincolo: «{tool}» escluso in modo esplicito, con il motivo",
                 tool in tocchi.ESCLUSI and m.startswith(f"«{tool}» è escluso dai tocchi:"), m)
    verifica("vincolo: dimentica, pc_guarda, anagrafica_salva e richiesta_tutore passerebbero le sole condizioni",
             all(tocchi._condizioni(n) is None for n in ("dimentica", "pc_guarda", "anagrafica_salva",
                                                         "richiesta_tutore", "lavoro_rispondi")))
    verifica("vincolo: ogni escluso è un tool vero della politica (niente nomi sbagliati)",
             all(n in politica.CLASSI for n in tocchi.ESCLUSI), str([n for n in tocchi.ESCLUSI if n not in politica.CLASSI]))
    verifica("vincolo: un tool sia toccabile sia escluso è un errore dell'elenco",
             "dimentica: è sia toccabile sia escluso" in tocchi.controlla(
                 toccabili={**tocchi.TOCCABILI, "dimentica": tocchi.Toccabile("prova")}))
    verifica("vincolo: un toccabile che non passa le condizioni è un errore dell'elenco",
             any(e.startswith("casa_comando:") and "pericoloso" in e for e in tocchi.controlla(
                 toccabili={**tocchi.TOCCABILI, "casa_comando": tocchi.Toccabile("prova")})))
    verifica("vincolo: un tocco senza bersaglio su un tool che lo vuole è un errore dell'elenco",
             tocchi.controlla({"x": tocchi.Tocco("agenda_annulla", None)})
             == ["x: «agenda_annulla» si tocca solo con un bersaglio"])
    # Le condizioni di prima, come difesa in più (con il tool messo per prova fra i toccabili)
    casi = {"casa_comando": "pericoloso", "tool_inventato": "classe", "web_cerca": "non fidati",
            "lavoro_annulla": "irreversibili", "registra_utente": "pericoloso"}
    for tool, parola in casi.items():
        m = tocchi._condizioni(tool) or ""
        verifica(f"vincolo: le condizioni rifiutano «{tool}» ({parola})", parola in m, m)
        verifica(f"vincolo: «{tool}» non ammesso dall'elenco", tocchi.ammesso(tool) is not None)
    vero = valore.EFFETTI["lista_togli"]
    valore.EFFETTI["lista_togli"] = valore.E3
    try:
        m = tocchi.ammesso("lista_togli") or ""
    finally:
        valore.EFFETTI["lista_togli"] = vero
    verifica("vincolo: un'azione con effetto E3 non ammessa (non si disfa)", "E2" in m, m)
    spec = ToolSpec(name="lista_togli", description="", parameters={}, func=lambda ctx: {},
                    classe="pericoloso")
    m = tocchi.ammesso("lista_togli", spec=spec) or ""
    verifica("vincolo: un ToolSpec che declassa il tool lo rende non ammesso", "pericoloso" in m, m)
    # La fonte non fidata anche per un'«azione» (#266): il risultato va nella storia senza busta
    for nome, sp in (("fonte", ToolSpec(name="lista_togli", description="", parameters={}, func=lambda ctx: {},
                                        risk="azione", classe="azione", fonte="web")),
                     ("non_fidato", ToolSpec(name="lista_togli", description="", parameters={}, func=lambda ctx: {},
                                             risk="azione", non_fidato=True))):
        m = tocchi.ammesso("lista_togli", spec=sp) or ""
        verifica(f"vincolo: un'«azione» con una fonte non fidata ({nome}) non ammessa",
                 politica.classe_di("lista_togli", sp).classe == politica.AZIONE and "non fidati" in m, m)
    vera = politica.CLASSI["timer_imposta"]
    politica.CLASSI["timer_imposta"] = dataclasses.replace(vera, fonte="web")
    try:
        m = tocchi.ammesso("timer_imposta") or ""
    finally:
        politica.CLASSI["timer_imposta"] = vera
    verifica("vincolo: un'«azione» della tabella con una fonte non fidata non ammessa", "non fidati" in m, m)
    # Con lo ToolSpec del registro: un tool solo per chi amministra vuole la sua voce
    sp = ToolSpec(name="lista_togli", description="", parameters={}, func=lambda ctx: {},
                  risk="azione", levels=frozenset({"amministra"}))
    m = tocchi.ammesso("lista_togli", spec=sp) or ""
    verifica("vincolo: un toccabile che il registro dà solo a chi amministra non ammesso", "voce" in m, m)
    # Un tocco nuovo su un tool non ammesso: il modulo non si importa (l'avvio si ferma)
    src = Path(tocchi.__file__).read_text(encoding="utf-8")
    cattivo = src.replace('Tocco("agenda_annulla", _timer_ferma', 'Tocco("casa_comando", _timer_ferma')
    mod = types.ModuleType("calliope.schermi._tocchi_prova")
    mod.__package__ = "calliope.schermi"
    errore = ""
    try:
        exec(compile(cattivo, "tocchi_prova.py", "exec"), mod.__dict__)
    except RuntimeError as e:
        errore = str(e)
    verifica("vincolo: un tocco su un tool non ammesso ferma l'import del modulo",
             cattivo != src and "timer_ferma" in errore and "casa_comando" in errore, errore)
    # Un tool nuovo che le condizioni ammetterebbero ma che non è fra i toccabili, ed escluso (#266)
    for tool, parola in (("lista_aggiungi", "toccabili"), ("dimentica", "escluso")):
        cattivo = src.replace('Tocco("lista_togli", _spunta_lista)', f'Tocco("{tool}", _spunta_lista)')
        mod = types.ModuleType("calliope.schermi._tocchi_prova")
        mod.__package__ = "calliope.schermi"
        errore = ""
        try:
            exec(compile(cattivo, "tocchi_prova.py", "exec"), mod.__dict__)
        except RuntimeError as e:
            errore = str(e)
        verifica(f"vincolo: un tocco nuovo su «{tool}» ({parola}) ferma l'import del modulo",
                 cattivo != src and "spunta_lista" in errore and parola in errore, errore)
    verifica("vincolo: controlla() su un elenco con un tool fuori dall'elenco",
             tocchi.controlla({"x": tocchi.Tocco("boh", None)}) == ["x: «boh» non è nell'elenco dei tool toccabili"])
    # prepara: un tocco che restituisce un altro tool è rifiutato
    metti_tocco("spunta_lista", tocchi.Tocco("lista_togli", lambda d, f: {
        "tool": "casa_comando", "argomenti": {}, "descrizione": "(prova)"}))
    try:
        r = tocchi.prepara({"tocco": "spunta_lista"}, None)
    finally:
        rimetti_tocchi()
    verifica("vincolo: prepara rifiuta un tocco che chiama un altro tool (403)",
             r.get("_stato") == 403 and "casa_comando" in r.get("motivo", ""), json.dumps(r, ensure_ascii=False))
    verifica("vincolo: non_ammesso per un tocco sconosciuto e per un tool diverso dal suo",
             tocchi.non_ammesso({"tocco": "boh", "tool": "lista_togli"}) == "tocco sconosciuto"
             and "lista_togli" in (tocchi.non_ammesso({"tocco": "timer_ferma", "tool": "lista_togli"}) or "")
             and tocchi.non_ammesso({"tocco": "timer_ferma", "tool": "agenda_annulla",
                                     "argomenti": {"cosa": "il timer"}}) is None)


# ─────────────────────────── 2. la vista per giorno ───────────────────────────
def ts(*a):
    return datetime.datetime(*a).timestamp()


def vista():
    ora = ts(2026, 10, 28, 23, 59, 0)
    voci = [
        {"id": 1, "kind": "timer", "label": "per la pasta", "due": ora + 30},
        {"id": 2, "kind": "promemoria", "label": "spegnere il forno", "due": ts(2026, 10, 28, 23, 59, 30)},
        {"id": 3, "kind": "appuntamento", "label": "dentista", "due": ts(2026, 10, 29, 0, 0, 0)},
        {"id": 4, "kind": "promemoria", "label": "chiamare il fabbro", "due": ts(2026, 10, 30, 8, 0)},
        {"id": 5, "kind": "appuntamento", "label": "riunione", "due": ts(2026, 11, 3, 23, 59)},
        {"id": 6, "kind": "promemoria", "label": "rinnovo", "due": ts(2026, 11, 4, 0, 0)},
        {"id": 7, "kind": "avviso", "label": "dentista", "due": ts(2026, 10, 28, 23, 59, 40)},
        {"id": 8, "kind": "promemoria", "label": "già passato", "due": ora - 5},
        {"id": 9, "kind": "timer", "label": "suonato", "due": ora - 1},
    ]
    g = per_giorno(voci, ora)
    ids = {k: [v["id"] for v in g[k]] for k in ("timer", "oggi", "domani", "settimana")}
    verifica("vista: timer a parte, solo quelli da suonare", ids["timer"] == [1], str(ids))
    verifica("vista: oggi fino a mezzanotte, mezzanotte in punto è domani",
             ids["oggi"] == [2] and ids["domani"] == [3], str(ids))
    verifica("vista: in settimana da dopodomani al sesto giorno; il settimo si conta soltanto",
             ids["settimana"] == [4, 5] and g["dopo"] == 1, f"{ids} dopo={g['dopo']}")
    verifica("vista: avvisi interni e voci già scadute fuori",
             all(7 not in v and 8 not in v for v in ids.values()))
    # Il cambio dell'ora legale (25/10/2026): il giorno si conta sulla data, non su 86400 s
    g = per_giorno([{"id": 1, "kind": "promemoria", "label": "x", "due": ts(2026, 10, 25, 23, 30)}],
                   ts(2026, 10, 24, 12, 0))
    verifica("vista: il giorno dopo anche a cavallo dell'ora legale", [v["id"] for v in g["domani"]] == [1])
    c = schede.giorno("bianca", "settimana", [voci[3], voci[4]], dopo=1)
    verifica("vista: la scheda del giorno (promemoria, personale, sua chiave, giorno e ora)",
             c["tipo"] == "promemoria" and c["visibilita"] == "personale" and c["chiave"] == "agenda:bianca:settimana"
             and c["titolo"] == "In settimana" and [v["quando"] for v in c["voci"]] == ["ven 30/10 alle 08:00",
                                                                                  "mar 03/11 alle 23:59"]
             and c["altre"] == 1 and c["sezione"] == "cose/agenda", json.dumps(c, ensure_ascii=False)[:300])
    c = schede.giorno("bianca", "oggi", [])
    verifica("vista: il giorno vuoto ha la sua frase", c["voci"] == [] and c["vuoto"] == "Niente oggi."
             and "altre" not in c)
    # La pagina con l'Agenda vera
    a = agenda_nuova("vista")
    adesso = time.time()
    a.add("timer", "per la pasta", adesso + 300, owner="dario", owner_name="Dario")
    a.add("timer", "di 3 minuti", adesso + 180)                    # di un ospite: senza nome
    a.add("promemoria", "chiamare il fabbro", adesso + 86400 * 1.5, owner="bianca", owner_name="Bianca")
    a.add("promemoria", "segreto di Dario", adesso + 600, owner="dario", owner_name="Dario")
    hub = types.SimpleNamespace(servizi=types.SimpleNamespace(agenda=a), tool_ctx=None)
    p = raccolte.pagina(hub, pr.BIANCA, "agenda")
    sc = p.get("schede") or []
    verifica("pagina: i timer di casa (in ordine) e i tre giorni",
             [c["tipo"] for c in sc] == ["timer", "timer", "promemoria", "promemoria", "promemoria"]
             and [c["timer"][0]["etichetta"] for c in sc[:2]] == ["di 3 minuti", "per la pasta"]
             and [c["chiave"] for c in sc[2:]] == ["agenda:bianca:oggi", "agenda:bianca:domani",
                                                   "agenda:bianca:settimana"], json.dumps(p, ensure_ascii=False)[:400])
    verifica("pagina: il timer con chi l'ha messo (quello di un ospite senza)",
             sc[1]["timer"][0].get("chi") == "Dario" and "chi" not in sc[0]["timer"][0]
             and sc[1]["chiave"] == schede.chiave_timer(a.items()[1]))
    testi = [v["testo"] for c in sc[2:] for v in c["voci"]]
    verifica("pagina: solo i promemoria della persona", testi == ["chiamare il fabbro"]
             and "segreto" not in json.dumps(p), str(testi))
    t = {x["id"]: x for x in raccolte.tessere(hub, pr.BIANCA, lambda m: None)}
    verifica("pagina: la tessera Agenda ha la pagina e conta i timer e le cose di oggi",
             t["agenda"]["pagina"] is True and t["agenda"]["conto"] == 2
             and t["agenda"]["stato"] == "2 timer · niente oggi", json.dumps(t["agenda"], ensure_ascii=False))
    verifica("pagina: senza agenda una nota", raccolte.pagina(types.SimpleNamespace(servizi=None, tool_ctx=None),
                                                             pr.BIANCA, "agenda").get("nota"))
    a.db.close()


# ─────────────────────────── 3. i tasti del timer ───────────────────────────
def tasti():
    a = agenda_nuova("tasti")
    adesso = time.time()
    tid = a.add("timer", "per la pasta", adesso + 300, owner="dario", owner_name="Dario")
    pid = a.add("promemoria", "fabbro", adesso + 300, owner="bianca", owner_name="Bianca")
    chiave = schede.chiave_timer(a.get(tid))
    fonti = types.SimpleNamespace(agenda=a)
    verifica("tasti: senza agenda 503", tocchi.prepara({"tocco": "timer_piu", "chiave": chiave},
                                                       types.SimpleNamespace()).get("_stato") == 503)
    verifica("tasti: chiave non valida 400",
             all(tocchi.prepara({"tocco": "timer_piu", "chiave": k}, fonti).get("_stato") == 400
                 for k in (None, 3, "lista:spesa", "timer:x-1", "timer:1")))
    created = int(a.get(tid)["created"] * 1000)
    for nome, k in (("un timer che non c'è", f"timer:{tid + 50}-{created}"),
                    ("l'id riusato (altra creazione)", f"timer:{tid}-{created + 1}"),
                    ("un promemoria (non è un timer di casa)", schede.chiave_timer(a.get(pid)))):
        r = tocchi.prepara({"tocco": "timer_ferma", "chiave": k}, fonti)
        verifica(f"tasti: {nome} 409", r.get("_stato") == 409 and "non c'è più" in r.get("errore", ""), json.dumps(r))
    r = tocchi.prepara({"tocco": "timer_piu", "chiave": " " + chiave}, fonti)
    verifica("tasti: «+1 minuto» → timer_imposta aggiungi un minuto, con il bersaglio",
             r.get("tool") == "timer_imposta"
             and r.get("argomenti") == {"durata": "1 minuto", "nome": "per la pasta", "cambia": "aggiungi"}
             and r.get("bersaglio") == {"timer": tid, "chiave": chiave}
             and r.get("descrizione") == "(Ho aggiunto un minuto al timer per la pasta toccando lo schermo.)",
             json.dumps(r, ensure_ascii=False))
    r = tocchi.prepara({"tocco": "timer_ferma", "chiave": chiave}, fonti)
    verifica("tasti: «Ferma» → agenda_annulla di quel timer, con il bersaglio",
             r.get("tool") == "agenda_annulla" and r.get("argomenti") == {"cosa": "il timer per la pasta"}
             and r.get("bersaglio") == {"timer": tid, "chiave": chiave}
             and r.get("descrizione") == "(Ho fermato il timer per la pasta toccando lo schermo.)",
             json.dumps(r, ensure_ascii=False))
    a.db.execute("UPDATE agenda SET due = ? WHERE id = ?", (adesso - 1, tid))
    a.db.commit()
    r = tocchi.prepara({"tocco": "timer_piu", "chiave": chiave}, fonti)
    verifica("tasti: un timer già scaduto 409", r.get("_stato") == 409, json.dumps(r))
    a.db.close()


# ─────────────────────────── 4. il ciclo ───────────────────────────
def scritto(prep, tocco, persona="bianca", sid=7):
    return {"tipo": "tocco", "tool": prep["tool"], "argomenti": prep["argomenti"],
            "descrizione": prep["descrizione"], "bersaglio": prep.get("bersaglio"), "tocco": tocco,
            "persona": persona, "schermo": "telefono", "stanza": None, "schermo_id": sid,
            "arrivato": time.time(), "pagina": {"chiave": (prep.get("bersaglio") or {}).get("chiave", "")}}


def ciclo():
    b, c, sc, liste, turni, voce, hub, _ = pr.prepara_ciclo()
    # Gli schermi della casa (revisione della PR #265): il telefono del tocco, il PC di Bianca e
    # la TV della cucina; `invia` raggiunge la cucina (con le automatiche spente nessuno)
    hub.abbinati = lambda: [{"id": 7, "nome": "telefono", "proprietario": "bianca"},
                            {"id": 8, "nome": "pc di bianca", "proprietario": "bianca"},
                            {"id": 9, "nome": "cucina"}]
    hub.automatiche = True

    def invia(scheda, mittente, forza=False):
        hub.a_tutti.append((scheda, mittente))
        return {"destinatari": ["cucina"] if hub.automatiche else []}
    hub.invia = invia
    a = agenda_nuova("ciclo")
    b.tool_ctx.agenda = a
    adesso = time.time()
    t5 = a.add("timer", "di 5 minuti", adesso + 300, owner="dario", owner_name="Dario")
    t10 = a.add("timer", "di 10 minuti", adesso + 600, owner="dario", owner_name="Dario")
    fonti = types.SimpleNamespace(agenda=a)
    k5 = schede.chiave_timer(a.get(t5))
    # Il turno a voce di prima: una proposta in sospeso, un «sì» già dato, un gioco
    ctx = b.tool_ctx
    ctx.tool_in_sospeso, ctx.politica_accettata, ctx.gioco_turno = "agenda_annulla", True, {"partita": 1}
    sc.current_speaker, sc.identified_by = "Dario", "voce"
    visti = []
    vero = c.s.tools.call

    def spia(nome, args, cx, livello):
        visti.append({k: getattr(cx, k, None) for k in ("tool_in_sospeso", "politica_accettata",
                                                        "gioco_turno", "tocco_bersaglio")})
        return vero(nome, args, cx, livello)
    c.s.tools.call = spia
    try:
        pr.tocca(c, scritto(tocchi.prepara({"tocco": "timer_piu", "chiave": k5}, fonti), "timer_piu"))
    finally:
        c.s.tools.call = vero
    r = turni[-1]
    verifica("ciclo: «+1 minuto» allunga il timer toccato di 60 s, non l'ultimo messo",
             abs(a.get(t5)["due"] - (adesso + 360)) < 1 and abs(a.get(t10)["due"] - (adesso + 600)) < 1,
             f"{a.get(t5)['due'] - adesso:.1f} {a.get(t10)['due'] - adesso:.1f}")
    verifica("ciclo: il registro dei turni con esito «tocco» e timer_imposta",
             r.get("esito") == "tocco" and r.get("canale") == "tocco" and r.get("tocco") == "timer_piu"
             and r["tool"][0]["nome"] == "timer_imposta" and r["tool"][0]["ok"] is True,
             json.dumps(r, ensure_ascii=False)[:300])
    verifica("ciclo: per il tocco niente proposta in sospeso, «sì» già dato né gioco; il bersaglio sì",
             visti and visti[0] == {"tool_in_sospeso": None, "politica_accettata": False, "gioco_turno": None,
                                    "tocco_bersaglio": {"timer": t5, "chiave": k5}}, str(visti))
    verifica("ciclo: dopo il tocco il contesto del turno di prima torna com'era",
             ctx.tool_in_sospeso == "agenda_annulla" and ctx.politica_accettata is True
             and ctx.gioco_turno == {"partita": 1} and ctx.tocco_bersaglio is None
             and sc.current_speaker == "Dario")
    coda = b.history[-4:]
    verifica("ciclo: nella storia il turno con timer_imposta, chiuso da Calliope",
             pr.ruoli(coda) == ["user", "assistant", "tool", "assistant"]
             and coda[1]["tool_calls"][0]["name"] == "timer_imposta"
             and "aggiunto 1 minuto" in coda[3]["content"], json.dumps(coda, ensure_ascii=False)[:400])
    inv = [s for sid, s in hub.inviate if s.get("tipo") == "timer" and sid == 7]
    verifica("ciclo: la scheda del timer aggiornata allo schermo del tocco, con la stessa chiave",
             inv and inv[-1]["chiave"] == k5 and abs(inv[-1]["timer"][0]["fine"] - (adesso + 360)) < 1,
             str(hub.inviate[-1:])[:300])
    casa = [(s, m) for s, m in hub.a_tutti if s.get("chiave") == k5]
    verifica("ciclo: il timer aggiornato anche agli schermi della casa, come dalla voce (non resta indietro)",
             len(casa) == 1 and casa[0][1].persona == "bianca" and casa[0][1].schermo == 7
             and casa[0][1].stanza is None and abs(casa[0][0]["timer"][0]["fine"] - (adesso + 360)) < 1,
             str(casa)[:300])
    verifica("ciclo: e all'altro schermo personale della persona, una volta sola per schermo",
             sorted(sid for sid, s in hub.inviate if s.get("chiave") == k5) == [7, 8], str(hub.inviate)[:300])
    hub.automatiche = False
    verifica("ciclo: l'evento «tocco» riuscito con la chiave toccata, nessuna frase detta",
             hub.eventi[-1][:2] == (7, "tocco") and hub.eventi[-1][2].get("ok") is True
             and hub.eventi[-1][2].get("pagina") == {"chiave": k5} and voce.detto == [])
    # «Ferma» sul primo: resta il secondo (l'ultimo messo)
    pr.tocca(c, scritto(tocchi.prepara({"tocco": "timer_ferma", "chiave": k5}, fonti), "timer_ferma"))
    r = turni[-1]
    verifica("ciclo: «Ferma» ferma il timer toccato e solo lui",
             a.get(t5) is None and a.get(t10) is not None and r.get("esito") == "tocco"
             and r["tool"][0]["nome"] == "agenda_annulla", json.dumps(r, ensure_ascii=False)[:300])
    inv = [s for sid, s in hub.inviate if s.get("tipo") == "timer" and sid == 7]
    verifica("ciclo: la scheda del timer fermato diventa «annullato alle …»",
             inv[-1]["chiave"] == k5 and inv[-1]["stato"] == "annullato")
    fermati = [sid for sid, s in hub.inviate if s.get("chiave") == k5 and s.get("stato") == "annullato"]
    verifica("ciclo: con le schede automatiche spente il timer fermato arriva lo stesso agli schermi "
             "della persona (la casa la decide l'hub)",
             sorted(fermati) == [7, 8] and any(s.get("stato") == "annullato" for s, _ in hub.a_tutti), str(fermati))
    verifica("ciclo: la storia chiude con la conferma di Calliope, mai due messaggi della persona di fila",
             b.history[-1]["role"] == "assistant" and "Ho annullato il timer" in b.history[-1]["content"]
             and not pr.due_user(b.history), json.dumps(b.history[-1], ensure_ascii=False))
    # Il timer suona mentre il tocco aspetta nella coda: niente timer nuovo al suo posto
    k10 = schede.chiave_timer(a.get(t10))
    prep = tocchi.prepara({"tocco": "timer_piu", "chiave": k10}, fonti)
    a.cancel_ids({t10})
    n_storia, prima = len(b.history), len(a.items())
    pr.tocca(c, scritto(prep, "timer_piu"))
    r, ev = turni[-1], hub.eventi[-1][2]
    verifica("ciclo: il timer suonato nel frattempo, rifiuto col motivo e nessun timer nuovo",
             r.get("esito") == "rifiutato" and "non c'è più" in r.get("motivo", "")
             and len(a.items()) == prima == 0 and ev.get("ok") is False and "non c'è più" in ev.get("errore", "")
             and len(b.history) == n_storia, json.dumps({"r": r, "ev": ev}, ensure_ascii=False)[:400])
    # Finito ma non ancora suonato mentre il tocco aspetta (#266, revisione della PR #270):
    # «+1 minuto» non lo allunga, suona come doveva
    t3 = a.add("timer", "di 3 minuti", time.time() + 180, owner="dario", owner_name="Dario")
    prep = tocchi.prepara({"tocco": "timer_piu", "chiave": schede.chiave_timer(a.get(t3))}, fonti)
    # Il tool da solo, col bersaglio del tocco: deciso. Il timer non si tocca nel database (il
    # thread dell'agenda lo farebbe suonare): per il tool l'orologio è oltre la fine
    import calliope.tools.builtin as builtin_mod
    vero_time = builtin_mod.time

    class Dopo:
        def __getattr__(self, nome):
            return getattr(vero_time, nome)

        @staticmethod
        def time():
            return vero_time.time() + 400
    due_prima = a.get(t3)["due"]
    ctx.tocco_bersaglio = prep["bersaglio"]
    sc.current_speaker, sc.identified_by = "Bianca", "schermo"
    builtin_mod.time = Dopo()
    try:
        diretto = json.loads(c.s.tools.call("timer_imposta", prep["argomenti"], ctx, "familiare"))
    finally:
        builtin_mod.time = vero_time
        ctx.tocco_bersaglio = None
        sc.current_speaker, sc.identified_by = "Dario", "voce"
    verifica("tool: «+1 minuto» su un timer finito e non ancora suonato non lo allunga, con la frase",
             diretto.get("ok") is False and "già finito" in diretto.get("risposta_finale", "")
             and a.get(t3) is not None and abs(a.get(t3)["due"] - due_prima) < 0.01,
             json.dumps(diretto, ensure_ascii=False)[:300])
    finito = time.time() - 1
    a.db.execute("UPDATE agenda SET due = ? WHERE id = ?", (finito, t3))
    a.db.commit()
    n_storia = len(b.history)
    pr.tocca(c, scritto(prep, "timer_piu"))
    r, ev = turni[-1], hub.eventi[-1][2]
    # Nel ciclo il timer può anche suonare prima del tocco (lo controlla il giro): allora «non c'è
    # più»; in tutti e due i casi non si allunga e non nasce un timer nuovo
    verifica("ciclo: «+1 minuto» su un timer finito e non ancora suonato: rifiutato, non allungato",
             r.get("esito") == "rifiutato"
             and ("già finito" in r.get("motivo", "") or "non c'è più" in r.get("motivo", ""))
             and (a.get(t3) is None or abs(a.get(t3)["due"] - finito) < 0.01) and len(a.items()) <= 1
             and ev.get("ok") is False and len(b.history) == n_storia,
             json.dumps({"motivo": r.get("motivo"), "ev": ev, "voci": len(a.items()), "t3": a.get(t3),
                         "finito": finito}, ensure_ascii=False, default=str)[:600])
    a.cancel_ids({t3})
    # Il vincolo nel ciclo: un tool non ammesso non si chiama nemmeno
    chiamati = []
    c.s.tools.call = lambda *x, **k: chiamati.append(x) or "{}"
    # Un tocco nell'elenco su un tool non ammesso (come se l'import non l'avesse fermato)
    metti_tocco("prova_pericolosa", tocchi.Tocco("registra_utente", None))
    try:
        for nome, item in (("un tool pericoloso dichiarato da un tocco", {
                                "tocco": "prova_pericolosa", "tool": "registra_utente", "argomenti": {"nome": "Ugo"}}),
                           ("un tool pericoloso", {"tocco": "spunta_lista", "tool": "registra_utente",
                                                   "argomenti": {"nome": "Ugo"}}),
                           ("un tool diverso da quello del tocco", {"tocco": "timer_ferma", "tool": "lista_togli",
                                                                    "argomenti": {"cose": "latte"}}),
                           ("un tocco sconosciuto", {"tocco": "svuota", "tool": "lista_togli",
                                                     "argomenti": {"cose": "latte"}})):
            n_storia, n_ev = len(b.history), len(hub.eventi)
            pr.tocca(c, {"tipo": "tocco", "descrizione": "(prova)", "persona": "dario", "schermo": "telefono",
                         "schermo_id": 7, "arrivato": time.time(), **item})
            r = turni[-1]
            ev = hub.eventi[-1][2] if len(hub.eventi) > n_ev else {}
            verifica(f"ciclo: {nome} rifiutato dal vincolo, senza chiamarlo",
                     r.get("esito") == "rifiutato" and r.get("regole") == ["tocco_non_ammesso"]
                     and not chiamati and len(b.history) == n_storia and ev.get("ok") is False
                     and "a voce" in ev.get("errore", ""), json.dumps({"r": r, "ev": ev}, ensure_ascii=False)[:300])
        verifica("ciclo: il motivo del vincolo nel registro (escluso dai tocchi)",
                 any("escluso dai tocchi" in (t.get("motivo") or "") for t in turni[-4:]))
        # Ogni escluso (#266), anche se un tocco lo dichiarasse: rifiutato nel ciclo senza chiamarlo
        for tool in sorted(tocchi.ESCLUSI):
            metti_tocco("prova_escluso", tocchi.Tocco(tool, None))
            n_storia = len(b.history)
            pr.tocca(c, {"tipo": "tocco", "descrizione": "(prova)", "persona": "bianca", "schermo": "telefono",
                         "schermo_id": 7, "arrivato": time.time(), "tocco": "prova_escluso", "tool": tool,
                         "argomenti": {}})
            r = turni[-1]
            verifica(f"ciclo: «{tool}» escluso, rifiutato dal vincolo senza chiamarlo",
                     r.get("regole") == ["tocco_non_ammesso"] and "escluso" in (r.get("motivo") or "")
                     and not chiamati and len(b.history) == n_storia, json.dumps(r, ensure_ascii=False)[:200])
        # Un tool fuori dall'elenco che le condizioni ammetterebbero (lista_aggiungi)
        metti_tocco("prova_escluso", tocchi.Tocco("lista_aggiungi", None))
        pr.tocca(c, {"tipo": "tocco", "descrizione": "(prova)", "persona": "bianca", "schermo": "telefono",
                     "schermo_id": 7, "arrivato": time.time(), "tocco": "prova_escluso", "tool": "lista_aggiungi",
                     "argomenti": {"cose": "latte"}})
        verifica("ciclo: un tool fuori dall'elenco dei toccabili rifiutato senza chiamarlo",
                 "toccabili" in (turni[-1].get("motivo") or "") and not chiamati, json.dumps(turni[-1])[:200])
    finally:
        c.s.tools.call = vero
        rimetti_tocchi()
    liste.db.close()
    a.db.close()


def senza_bersaglio_e_corsia():
    b, c, sc, liste, turni, voce, hub, _ = pr.prepara_ciclo()
    a = agenda_nuova("bersaglio")
    b.tool_ctx.agenda = a
    tid = a.add("timer", "di 5 minuti", time.time() + 300)
    chiamati = []
    vero = c.s.tools.call
    c.s.tools.call = lambda *x, **k: chiamati.append(x) or "{}"
    try:
        for bers in (None, {"timer": tid}, "timer:1-1"):
            n_ev = len(hub.eventi)
            pr.tocca(c, {"tipo": "tocco", "tool": "agenda_annulla", "argomenti": {"cosa": "tutti"},
                         "descrizione": "(prova)", "tocco": "timer_ferma", "bersaglio": bers,
                         "persona": "bianca", "schermo": "telefono", "schermo_id": 7, "arrivato": time.time()})
            r = turni[-1]
            verifica(f"bersaglio: un tocco del timer senza bersaglio valido ({bers!r}) rifiutato con la sua regola",
                     r.get("regole") == ["tocco_senza_bersaglio"] and not chiamati and a.get(tid) is not None
                     and len(hub.eventi) > n_ev and hub.eventi[-1][2].get("ok") is False, json.dumps(r)[:200])
    finally:
        c.s.tools.call = vero
    metti_tocco("timer_ferma", tocchi.Tocco("agenda_annulla", lambda d, f: {
        "tool": "agenda_annulla", "argomenti": {"cosa": "il timer"}, "descrizione": "(prova)"}, bersaglio=True))
    try:
        r = tocchi.prepara({"tocco": "timer_ferma"}, None)
    finally:
        rimetti_tocchi()
    verifica("bersaglio: prepara rifiuta un tocco del timer che ha perso il bersaglio (403)",
             r.get("_stato") == 403 and r.get("motivo") == "senza bersaglio", json.dumps(r, ensure_ascii=False))
    # Una corsia nuova nasce pulita, anche se si collega mentre il ciclo è dentro un tocco
    from calliope.main import contesto_corsia
    ctx = b.tool_ctx
    ctx.tool_in_sospeso, ctx.politica_accettata, ctx.gioco_turno = "agenda_annulla", True, {"partita": 1}
    ctx.tocco_bersaglio, ctx.user_text, ctx.regole = {"timer": tid, "chiave": "x"}, "(prova)", ["r"]
    nuovo = contesto_corsia(ctx, "sc", "sp")
    sporchi = {k: getattr(nuovo, k) for k in ("tool_in_sospeso", "politica_accettata", "gioco_turno",
                                              "tocco_bersaglio", "user_text", "regole", "politica",
                                              "si_breve", "errore_registro")
               if getattr(nuovo, k) not in (None, False, "", [])}
    verifica("corsia: una corsia nuova nasce pulita (niente bersaglio, proposta, «sì» o gioco della principale)",
             not sporchi and nuovo.agenda is a and nuovo.speaker_ctx == "sc" and nuovo.regole is not ctx.regole,
             str(sporchi))
    for k in c._CTX_TOCCO:
        if hasattr(nuovo, k) and k not in ("strumenti",):
            verifica(f"corsia: «{k}» del tocco non passa alla corsia nuova",
                     getattr(nuovo, k) in (None, False, "", []), repr(getattr(nuovo, k))[:80])
    liste.db.close()
    a.db.close()


class CicloFinto:
    """Il ciclo del server per una connessione: ciò che le arriva, senza asyncio."""

    def __init__(self):
        self.arrivati = []

    def call_soon_threadsafe(self, f, item):
        self.arrivati.append(item)


def numero_riusato():
    """Gli id degli schermi si riusano (#266, seconda revisione della PR #270): la tabella ha
    `INTEGER PRIMARY KEY` senza AUTOINCREMENT e la revoca cancella la riga. Una revoca e un
    abbinamento fatti da terminale (un secondo `ArchivioSchermi`, come `python -m calliope.schermi`)
    danno il numero dello schermo tolto a uno schermo nuovo di un'altra persona: né «Ferma» né il
    collegamento gli mandano niente dello schermo di prima, e la pagina vecchia riceve «revocato»."""
    from calliope.schermi import Mittente
    b, c, sc, liste, turni, voce, finto, _ = pr.prepara_ciclo()
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "memoria-riuso.db")
    cfg.schermi_stanza = "cucina"
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    hub.profilo = c.s.registry.by_id
    terminale = ArchivioSchermi(cfg.memory_db)          # un altro processo, sullo stesso file
    giochi_via = []
    hub.giochi = types.SimpleNamespace(schermi_via=lambda v: giochi_via.append(set(v)))
    tel_b, _ = hub.archivio.crea_con_token("telefono", proprietario="bianca", proprietario_nome="Bianca")
    tel_d, _ = hub.archivio.crea_con_token("telefono", proprietario="dario", proprietario_nome="Dario")
    cucina, _ = hub.archivio.crea_con_token("cucina")
    hub._rinfresca()
    c.s.schermi = b.tool_ctx.schermi = hub
    c.ingresso = hub.ingresso
    a = agenda_nuova("riuso")
    b.tool_ctx.agenda = a
    fonti = types.SimpleNamespace(agenda=a)
    sc.current_speaker, sc.identified_by = "Bianca", "voce"

    def con(sid, k):
        return [s for s in hub.storia(sid) if s.get("chiave") == k]

    def ferma(k, sid):
        item = scritto(tocchi.prepara({"tocco": "timer_ferma", "chiave": k}, fonti), "timer_ferma",
                       persona="dario", sid=sid)
        item["stanza"] = "telefono"
        pr.tocca(c, item)
        return turni[-1]

    try:
        # 1. La cucina revocata da terminale, il PC nuovo di Bianca col suo numero; «Ferma» con
        #    l'elenco in memoria ancora vecchio (i 5 s della cache) e con l'elenco riletto
        for giro, riletto in (("con l'elenco in memoria vecchio", False), ("con l'elenco riletto", True)):
            tid = a.add("timer", f"della pasta {giro}", time.time() + 300, owner="dario", owner_name="Dario")
            k = schede.chiave_timer(a.get(tid))
            ultimo = max(s["id"] for s in hub.abbinati())
            stanza_tv = next(s for s in hub.abbinati() if s["id"] == ultimo and not s.get("proprietario"))["stanza"]
            hub.invia(schede.timer(a.get(tid)), Mittente(persona="dario", nome="Dario", livello="amministra",
                                                         certo=True, stanza=stanza_tv))
            verifica(f"riuso ({giro}): il timer messo a voce è sulla TV, l'ultimo numero",
                     hub.dove(k) == {ultimo}, str(hub.dove(k)))
            assert terminale.revoca(ultimo)
            nuovo, _ = terminale.crea_con_token("studio", proprietario="bianca", proprietario_nome="Bianca")
            verifica(f"riuso ({giro}): il PC nuovo di Bianca riprende il numero della TV revocata",
                     nuovo["id"] == ultimo, f"{nuovo['id']} {ultimo}")
            if riletto:
                hub._rinfresca()
            r = ferma(k, tel_d["id"])
            # Il PC nuovo si collega: il server rilegge l'elenco se la sessione non torna (_schermo_sessione)
            hub._rinfresca()
            riga = next(s for s in hub.abbinati() if s["id"] == ultimo)
            loop = CicloFinto()
            conn, storia = hub.collega(riga, loop)
            verifica(f"riuso ({giro}): «Ferma» dal telefono di Dario non arriva al PC nuovo di Bianca",
                     r.get("esito") == "tocco" and not con(ultimo, k) and not [x for x in storia if x.get("chiave") == k]
                     and ultimo not in hub.dove(k), f"{r.get('esito')} {hub.dove(k)} {[x.get('chiave') for x in storia]}")
            hub.scollega(conn)
            # Lo schermo nuovo diventa la TV per il giro dopo (stanza, non personale)
            assert terminale.revoca(ultimo)
            terminale.crea_con_token(f"cucina{2 if riletto else 1}")
            hub._rinfresca()
            hub.abbinati()
        # 2. La scheda personale di Dario in memoria sul suo telefono, la pagina vecchia aperta;
        #    il telefono revocato da terminale e quello nuovo di Bianca col suo numero
        tel_d2, _ = hub.archivio.crea_con_token("telefono", proprietario="dario", proprietario_nome="Dario")
        hub._rinfresca()
        sid = tel_d2["id"]
        assert sid == max(s["id"] for s in hub.abbinati())
        riga_d = next(s for s in hub.abbinati() if s["id"] == sid)
        hub.invia_a(sid, {"tipo": "testo", "chiave": "nota:privata", "visibilita": "personale",
                          "testo": "di Dario"})
        loop_vecchio = CicloFinto()
        vecchia, _ = hub.collega(riga_d, loop_vecchio)
        assert terminale.revoca(sid)
        nuovo, _ = terminale.crea_con_token("telefono", proprietario="bianca", proprietario_nome="Bianca")
        verifica("riuso: il telefono nuovo di Bianca riprende il numero di quello di Dario", nuovo["id"] == sid)
        hub._rinfresca()
        riga_b = next(s for s in hub.abbinati() if s["id"] == sid)
        loop = CicloFinto()
        conn, storia = hub.collega(riga_b, loop)
        verifica("riuso: al collegamento il telefono nuovo di Bianca non riceve la scheda personale di Dario",
                 riga_b["proprietario"] == "bianca" and not [x for x in storia if x.get("chiave") == "nota:privata"],
                 str([x.get("chiave") for x in storia]))
        verifica("riuso: la pagina vecchia del telefono di Dario riceve «revocato» e non è più collegata",
                 ("revocato", "{}") in loop_vecchio.arrivati and vecchia not in hub._conn.get(sid, [])
                 and conn in hub._conn.get(sid, []), str(loop_vecchio.arrivati))
        hub.invia_a(sid, {"tipo": "testo", "chiave": "nota:bianca", "visibilita": "personale", "testo": "di Bianca"})
        verifica("riuso: ciò che va al telefono nuovo arriva solo alla sua pagina, non a quella vecchia di Dario",
                 not [x for x in loop_vecchio.arrivati if "nota:bianca" in str(x)]
                 and [x for x in loop.arrivati if "nota:bianca" in str(x)])
        verifica("riuso: valido() col momento dell'abbinamento distingue lo schermo di prima",
                 hub.valido(sid) and hub.valido(sid, riga_b["creato"]) and not hub.valido(sid, riga_d["creato"]))
        verifica("riuso: anche i giochi tolgono i posti del numero riusato (Giochi.schermi_via)",
                 any(sid in v for v in giochi_via), str(giochi_via))
        hub.scollega(conn)
    finally:
        liste.db.close()
        a.db.close()


def hub_vero():
    """La scheda pubblica del timer con l'hub vero e due stanze (#266, nota 3 della revisione
    della PR #265, e revisione della PR #270). Una scheda che c'è già (stessa chiave) si aggiorna
    dove era andata, più gli schermi di chi tocca: il timer messo a voce in cucina e fermato dal
    telefono (la cui stanza è «telefono») arriva alla TV della cucina e non al telefono di un altro
    familiare. Una scheda mai vista va come a voce: stanza predefinita, senza quella tutti, con la
    stanza dello schermo a quella; mai agli schermi personali di altre persone. Il mittente col
    livello vero, limitato come lo scritto. La traccia chiave → schermi ha un tetto e dimentica gli
    schermi revocati."""
    from calliope.schermi import Mittente
    b, c, sc, liste, turni, voce, finto, _ = pr.prepara_ciclo()
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "memoria-hub.db")
    cfg.schermi_stanza = "cucina"
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    hub.profilo = c.s.registry.by_id
    cucina, _ = hub.archivio.crea_con_token("cucina")
    salotto, _ = hub.archivio.crea_con_token("salotto")
    tel, _ = hub.archivio.crea_con_token("telefono", proprietario="dario", proprietario_nome="Dario")
    pc_d, _ = hub.archivio.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario")
    tel_b, _ = hub.archivio.crea_con_token("telefono", proprietario="bianca", proprietario_nome="Bianca")
    hub._rinfresca()
    c.s.schermi = b.tool_ctx.schermi = hub
    c.ingresso = hub.ingresso
    mittenti = []
    vero_aggiorna = hub.aggiorna

    def spia(scheda, mittente):
        mittenti.append(mittente)
        return vero_aggiorna(scheda, mittente)
    hub.aggiorna = spia
    a = agenda_nuova("hub-vero")
    b.tool_ctx.agenda = a
    fonti = types.SimpleNamespace(agenda=a)

    def con(sid, k):
        return [s for s in hub.storia(sid) if s.get("chiave") == k]

    def nuovo_timer(nome):
        tid = a.add("timer", nome, time.time() + 300, owner="dario", owner_name="Dario")
        return tid, schede.chiave_timer(a.get(tid))

    def tocca_timer(k, stanza, tocco="timer_piu"):
        item = scritto(tocchi.prepara({"tocco": tocco, "chiave": k}, fonti), tocco,
                       persona="dario", sid=tel["id"])
        item["stanza"] = stanza
        n = len(mittenti)
        pr.tocca(c, item)
        return turni[-1], mittenti[n:]

    def giro(stanza, nome):
        _, k = nuovo_timer(nome)
        r, m = tocca_timer(k, stanza)
        return k, r, m

    try:
        sc.current_speaker, sc.identified_by = "Bianca", "voce"
        # Il caso vero: il timer messo a voce in cucina, poi fermato dal telefono (stanza «telefono»)
        tid, k = nuovo_timer("della pasta")
        hub.invia(schede.timer(a.get(tid)), Mittente(persona="dario", nome="Dario", livello="amministra",
                                                     certo=True, stanza="cucina"))
        verifica("hub vero: il timer messo a voce in cucina è sulla TV della cucina, non sui telefoni",
                 con(cucina["id"], k) and not con(tel["id"], k) and not con(tel_b["id"], k)
                 and hub.dove(k) == {cucina["id"]}, str(hub.dove(k)))
        r, m = tocca_timer(k, "telefono", "timer_ferma")
        fermata = [s for s in con(cucina["id"], k) if s.get("stato") == "annullato"]
        verifica("hub vero: «Ferma» dal telefono aggiorna la TV della cucina, dove la scheda c'era",
                 r.get("esito") == "tocco" and fermata and a.get(tid) is None,
                 json.dumps(r, ensure_ascii=False)[:200])
        verifica("hub vero: e gli schermi di chi tocca, non il telefono di Bianca con la stessa «stanza» "
                 "né il salotto, che non l'avevano",
                 con(tel["id"], k) and con(pc_d["id"], k) and not con(tel_b["id"], k) and not con(salotto["id"], k))
        verifica("hub vero: il mittente col livello vero limitato come lo scritto (chi amministra: familiare)",
                 m and m[-1].livello == "familiare" and m[-1].persona == "dario" and m[-1].certo
                 and m[-1].stanza == "telefono" and m[-1].schermo == tel["id"], str(m))
        verifica("hub vero: chi tocca non ha preso il livello di chi parlava a voce prima",
                 r.get("livello") == "familiare" and sc.current_speaker == "Bianca")
        # Una scheda mai vista (Calliope riaccesa dopo che il timer era stato messo): come a voce
        k, r, m = giro(None, "di 5 minuti")
        verifica("hub vero: una scheda mai vista, senza la stanza dello schermo, va alla stanza predefinita "
                 "(cucina), non al salotto", r.get("esito") == "tocco" and con(cucina["id"], k)
                 and not con(salotto["id"], k), f"{len(con(cucina['id'], k))} {len(con(salotto['id'], k))}")
        verifica("hub vero: e agli schermi personali di chi tocca, non a quelli di un'altra persona",
                 con(tel["id"], k) and con(pc_d["id"], k) and not con(tel_b["id"], k))
        cfg.schermi_stanza = ""
        k, r, m = giro(None, "di 7 minuti")
        verifica("hub vero: senza stanza predefinita a tutti gli schermi di stanza, non al telefono di Bianca",
                 r.get("esito") == "tocco" and con(cucina["id"], k) and con(salotto["id"], k)
                 and not con(tel_b["id"], k), f"{r.get('esito')} {hub.dove(k)}")
        cfg.schermi_stanza = "cucina"
        k, r, m = giro("salotto", "di 9 minuti")
        verifica("hub vero: con la stanza dello schermo il timer va a quella stanza (salotto), non alla cucina",
                 r.get("esito") == "tocco" and con(salotto["id"], k) and not con(cucina["id"], k)
                 and con(tel["id"], k), f"{r.get('esito')}")
        k, r, m = giro("telefono", "di 11 minuti")
        verifica("hub vero: dalla «stanza» telefono una scheda mai vista non va al telefono di Bianca",
                 r.get("esito") == "tocco" and con(tel["id"], k) and not con(tel_b["id"], k), str(hub.dove(k)))
        # La traccia: un tetto, e uno schermo revocato non c'è più
        hub._DOVE_MAX = 3
        for n in range(5):
            hub.invia_a(salotto["id"], {"tipo": "testo", "testo": "x", "chiave": f"prova:{n}"})
        verifica("hub vero: la traccia chiave → schermi ha un tetto (le più vecchie escono)",
                 len(hub._dove) == 3 and not hub.dove("prova:0") and hub.dove("prova:4") == {salotto["id"]},
                 str(list(hub._dove)))
        hub.avvisa_revoca([salotto["id"]])
        verifica("hub vero: uno schermo revocato esce dalla traccia", not hub.dove("prova:4"))
    finally:
        liste.db.close()
        a.db.close()


def conv_archivio():
    """`conv_archivio` segue la conversazione del tocco e del modulo (#266, nota 4 della revisione
    della PR #265 e revisione della PR #270): dopo è quella della persona, non quella di prima."""
    b, c, sc, liste, turni, voce, hub, _ = pr.prepara_ciclo()
    pr.CORRENTE["liste"] = liste
    b.tool_ctx.conv_archivio = "conversazione-di-prima"
    visti = []
    vero = c.s.tools.call

    def spia(nome, args, cx, livello):
        visti.append(getattr(cx, "conv_archivio", None))
        return vero(nome, args, cx, livello)
    c.s.tools.call = spia
    try:
        pr.tocca(c, pr.voce_tocco("bianca"))
    finally:
        c.s.tools.call = vero
    attesa = getattr(b.conv, "id_archivio", None)
    verifica("conv_archivio: il tool del tocco vede la conversazione della persona, non quella di prima",
             turni[-1].get("esito") == "tocco" and visti and visti[0] != "conversazione-di-prima"
             and visti[0] == attesa, f"{visti} {attesa!r}")
    verifica("conv_archivio: e resta quella dopo il tocco, come la conversazione di Brain",
             b.tool_ctx.conv_archivio == getattr(b.conv, "id_archivio", None) != "conversazione-di-prima")
    # Il modulo dallo schermo: il tool che l'aveva chiesto vede la conversazione della persona
    import calliope.ciclo as ciclo_mod

    class Fermo(Exception):
        pass

    def completa(hub_, scritto_, brain, n):
        visti.append(("modulo", brain.tool_ctx.conv_archivio, getattr(brain.conv, "id_archivio", None)))
        raise Fermo
    vera = ciclo_mod.completa_modulo
    ciclo_mod.completa_modulo = completa
    b.tool_ctx.conv_archivio = "conversazione-di-prima"
    try:
        c._modulo_dallo_schermo(types.SimpleNamespace(scritto={"tipo": "modulo", "persona": "dario"}))
    except Fermo:
        pass
    finally:
        ciclo_mod.completa_modulo = vera
    m = [v for v in visti if isinstance(v, tuple)]
    verifica("conv_archivio: anche il modulo dallo schermo vede la conversazione della persona",
             m and m[-1][1] != "conversazione-di-prima" and m[-1][1] == m[-1][2], str(m))
    liste.db.close()


# ─────────────────────────── 5. il server ───────────────────────────
def server():
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "memoria.db")
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    reg = pr.Persone()
    hub.profilo = reg.by_id
    a = agenda_nuova("server")
    tid = a.add("timer", "per le uova", time.time() + 300, owner="bianca", owner_name="Bianca")
    chiave = schede.chiave_timer(a.get(tid))
    hub.tool_ctx = ToolContext(cfg=cfg, speakers=reg, speaker_ctx=None, speaker=None, agenda=a)
    srv = ServerSchermi(hub, "127.0.0.1", 0, attesa_porta_s=5).avvia()
    hub.server = srv
    try:
        _, tok = hub.archivio.crea_con_token("telefono", proprietario="bianca", proprietario_nome="Bianca")
        hub._rinfresca()
        port = srv.port
        sess = pr.chiedi(port, "/api/accedi", token=tok)[1].get("sessione")
        st, d = pr.chiedi(port, "/api/raccolte", sess, corpo={"raccolta": "agenda"})
        verifica("server: la pagina Agenda dal servizio",
                 st == 200 and [c.get("tipo") for c in d.get("schede") or []][:1] == ["timer"]
                 and (d["schede"][0].get("chiave") == chiave), f"{st} {json.dumps(d)[:300]}")
        st, d = pr.chiedi(port, "/api/tocco", sess, corpo={"tocco": "timer_piu", "chiave": "timer:999-1"})
        verifica("server: il tocco su un timer che non c'è 409, niente al ciclo",
                 st == 409 and hub.ingresso.vuoto(), f"{st} {d}")
        st, d = pr.chiedi(port, "/api/tocco", sess, corpo={"tocco": "timer_ferma", "chiave": chiave})
        item = hub.ingresso.prendi() or {}
        verifica("server: «Ferma» nell'ingresso con il tool, il bersaglio e la chiave della pagina",
                 st == 200 and item.get("tool") == "agenda_annulla" and item.get("tocco") == "timer_ferma"
                 and item.get("bersaglio") == {"timer": tid, "chiave": chiave}
                 and item.get("pagina") == {"chiave": chiave} and item.get("persona") == "bianca",
                 f"{st} {d} {item}")
        verifica("server: il tocco non tocca l'agenda (la cambia il ciclo)", a.get(tid) is not None)
        codici = [pr.chiedi(port, "/api/tocco", sess, corpo={"tocco": "timer_piu",
                                                            "chiave": "timer:999-1"})[0] for _ in range(30)]
        verifica("server: oltre 30 tocchi al minuto 429", codici[-1] == 429 and 409 in codici, str(codici[-3:]))
        # Il numero riusato (#266, seconda revisione della PR #270): il telefono di Bianca revocato
        # da terminale e uno nuovo di Dario col suo numero; la sessione della pagina vecchia non
        # diventa lo schermo nuovo, quella nuova sì
        terminale = ArchivioSchermi(cfg.memory_db)
        vecchio = hub.archivio.per_token(tok)
        assert terminale.revoca(vecchio["id"])
        nuovo, tok_d = terminale.crea_con_token("telefono", proprietario="dario", proprietario_nome="Dario")
        # Riletto l'elenco (al più 5 s dopo una revoca da terminale, come prima di questa correzione)
        hub._rinfresca()
        st, d = pr.chiedi(port, "/api/raccolte", sess, corpo={"raccolta": "agenda"})
        verifica("server: la sessione del telefono revocato non vale per lo schermo nuovo col suo numero",
                 nuovo["id"] == vecchio["id"] and st == 401, f"{nuovo['id']} {vecchio['id']} {st} {d}")
        sess_d = pr.chiedi(port, "/api/accedi", token=tok_d)[1].get("sessione")
        st, d = pr.chiedi(port, "/api/raccolte", sess_d, corpo={"raccolta": "agenda"})
        verifica("server: la sessione del telefono nuovo vale subito (l'elenco in memoria si rilegge)",
                 st == 200, f"{st} {d}")
        st, _ = pr.chiedi(port, "/api/raccolte", sess, corpo={"raccolta": "agenda"})
        verifica("server: e la sessione vecchia resta tolta", st == 401, str(st))
    finally:
        srv.ferma()
        a.db.close()


def main():
    try:
        print("— 1. il vincolo dei tocchi")
        vincolo()
        print("— 2. la vista per giorno")
        vista()
        print("— 3. i tasti del timer")
        tasti()
        print("— 4. il ciclo")
        ciclo()
        senza_bersaglio_e_corsia()
        hub_vero()
        numero_riusato()
        conv_archivio()
        print("— 5. il server")
        server()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{len(ERRORI)} errori" if ERRORI else "\ntutto ok")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
