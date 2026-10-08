"""
I tool dei minori (05/10/2026, calliope/minori.py, docs/ricerche/2026-10-05-minori.md).

- compiti_aiuto(esercizio, espressione, risposta, giusta): per un minore con i compiti
  guidati registra l'esercizio e conta i tentativi; controlla i conti con il valutatore di
  `calcola` e non dice mai la soluzione prima di `minori_compiti_tentativi` risposte
  sbagliate. Allora la soluzione si può spiegare, Calliope dice che lo dirà ai tutori e i
  tutori ricevono l'avviso (minori.Avvisi).
- minore_gestisci(nome, azione, valore): il preset di un minore. Leggerlo può anche il minore
  stesso; cambiarlo (preset, orari, estensioni, autorizzazioni a tempo, data di nascita,
  tutori) solo un suo tutore o chi amministra, riconosciuto dalla voce nella frase.
"""

from __future__ import annotations

import ast
import math

from .. import minori as M
from ..conferme import serve_conferma
from .spec import ToolContext, ToolSpec, note_rule
from ..testi import FAMILY, MESI, NIENTE


def _final(text: str, **extra) -> dict:
    return {"ok": True, **extra, "conferma": text, "risposta_finale": text}


def _valuta(espressione: str):
    """Il valore di un'espressione con il valutatore sicuro di calcola; None se non va."""
    from .builtin import _eval_node
    expr = (espressione or "").strip().replace("×", "*").replace("÷", "/").replace("^", "**")
    expr = expr.replace(":", "/")
    import re
    expr = re.sub(r"(?<=\d),(?=\d)", ".", expr)
    if not expr or len(expr) > 200:
        return None
    try:
        v = _eval_node(ast.parse(expr, mode="eval"))
    except Exception:  # noqa: BLE001
        return None
    return v if isinstance(v, (int, float)) and math.isfinite(v) else None


def _numero(testo) -> float | None:
    """Un numero detto dal ragazzo: «5/4», «1,25», «uno virgola venticinque» no (cifre)."""
    import re
    t = str(testo or "").strip().replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?(?:\s*/\s*\d+)?", t)
    if not m:
        return None
    s = m.group(0).replace(" ", "")
    if "/" in s:
        a, b = s.split("/")
        return float(a) / float(b) if float(b) else None
    return float(s)


# L'esercizio in corso come azione in sospeso (Brain.set_pending con «messaggio»): il testo
# arriva subito prima della frase del ragazzo, dove il modello lo legge di sicuro. Banco del
# 05/10: con il solo dato del turno gemma4 e4b non richiamava mai compiti_aiuto sulle
# risposte (0 su 8), giudicandole da sé e arrivando a dire la soluzione
COMPITI_MSG = ("Compiti in corso, messaggio di sistema: stai aiutando con l'esercizio «{e}» "
               "senza dare la soluzione. Se in questa frase dice un risultato o una risposta, "
               "chiama subito compiti_aiuto con esercizio={ej}{expr} e risposta (come l'ha "
               "detta), senza dire tu se è giusta. Se parla d'altro, rispondi normalmente.")


def _in_corso(e: dict, out: dict) -> dict:
    import json as _json
    expr = f", espressione={_json.dumps(e['espressione'])}" if e.get("espressione") else ""
    out["in_sospeso"] = {"tool": "compiti_aiuto", "argomenti": {"esercizio": e["testo"]},
                         "domanda": "?", "cosa": "l'esercizio",
                         "messaggio": COMPITI_MSG.format(e=e["testo"], ej=_json.dumps(
                             e["testo"], ensure_ascii=False), expr=expr)}
    return out


def _esercizio_nuovo(esercizio: str, espressione: str, detta: str, aperto: dict) -> bool:
    """La chiamata porta un esercizio diverso da quello aperto (e non la risposta detta)?"""
    import re
    expr = re.sub(r"\s+", "", str(espressione or ""))
    if expr and expr != aperto.get("espressione") and re.search(r"[-+*/x×:^]", expr[1:]):
        v, n = _valuta(expr), _numero(detta)
        return not (v is not None and n is not None and abs(v - n) < 1e-9)
    t = str(esercizio or "").strip()
    if t and not expr:
        from ..minori import _norm
        nt = _norm(t)
        return (nt != _norm(detta) and nt != aperto.get("chiave")
                and bool(re.search(r"[-+*/×:]|\b(?:per|più|meno|diviso)\b", nt))
                and _numero(nt) != _numero(detta))
    return False


def _compiti_aiuto(ctx: ToolContext, esercizio: str = "", espressione: str = "",
                   risposta: str = "", giusta=None) -> dict:
    prof = M.profilo(ctx)
    p = M.preset(prof) if prof is not None else None
    if p is None or p.get("compiti") != "guida":
        return {"ok": False, "fatto": "non serve: chi parla non ha i compiti guidati",
                "cosa_fare": "rispondi normalmente, con i tool di sempre"}
    comp = M.compiti()
    detta = str(risposta or "").strip()
    aperto = comp.aperto(prof.id)
    # Una risposta del ragazzo mentre c'è un esercizio aperto: va a quello, a meno che il
    # modello non porti un esercizio nuovo vero (un'espressione con un'operazione, diversa
    # dalla risposta). Banco del 05/10 sulla DGX: il 26B passava la risposta come esercizio
    # ed espressione («1», «2/3»), che diventavano esercizi nuovi «risolti»
    if detta and aperto is not None and not _esercizio_nuovo(esercizio, espressione, detta, aperto):
        note_rule(ctx, "compiti_stesso_esercizio")
        e = aperto
    else:
        esercizio = str(esercizio or "").strip() or str(espressione or "").strip()
        if not esercizio:
            return {"ok": False, "errore": "manca l'esercizio",
                    "cosa_fare": "chiedi in breve qual è l'esercizio"}
        e = comp.apri(prof.id, esercizio, espressione)
    massimo = comp.massimo
    av = M.avvisi()
    if av is not None and e["tentativi"] == 0 and not e.get("contato"):
        e["contato"] = True
        try:
            av.compito(prof, e["testo"])
        except Exception:  # noqa: BLE001
            pass
    note_rule(ctx, "compiti_guida")
    if not detta:
        return _in_corso(e, {"ok": True, "esercizio": e["testo"], "tentativi": e["tentativi"],
                             "massimo": massimo,
                             "cosa_fare": "Non dire la soluzione. Fai una domanda guida o dai un "
                                          "indizio sul primo passo, poi chiedigli quanto gli "
                                          "viene."})
    corretta = None
    if e.get("espressione"):
        v, n = _valuta(e["espressione"]), _numero(detta)
        if v is not None and n is not None:
            corretta = abs(v - n) <= 1e-6 * max(1.0, abs(v))
    # Con un'espressione decide il conto del programma, non il «giusta» del modello
    if corretta is None and giusta is not None and not e.get("espressione"):
        corretta = giusta is True or str(giusta).strip().lower() in ("true", "sì", "si", "1")
    if corretta:
        e["risolto"] = True
        return {"ok": True, "giusta": True, "esercizio": e["testo"],
                "cosa_fare": "È giusta: diglielo e fagli i complimenti, poi spiega in breve "
                             "perché."}
    if corretta is None:
        return _in_corso(e, {"ok": True, "giusta": None, "esercizio": e["testo"],
                             "cosa_fare": "Controlla tu la sua risposta senza dire la soluzione; "
                                          "se è sbagliata richiama compiti_aiuto con "
                                          "giusta=false."})
    e["tentativi"] += 1
    if e["tentativi"] < massimo:
        return _in_corso(e, {"ok": True, "giusta": False, "tentativi": e["tentativi"],
                             "massimo": massimo,
                             "cosa_fare": "Non è giusta. NON dire la soluzione né il risultato: "
                                          "digli con gentilezza che non è ancora giusta e dai un "
                                          "indizio diverso dal precedente, o una domanda "
                                          "guida."})
    # Dopo il massimo: si spiega, e i tutori lo sanno davvero
    e["spiegato"] = True
    if av is not None and not e.get("avvisato"):
        e["avvisato"] = True
        try:
            av.compito(prof, e["testo"], soluzione=True)
            av.manda(prof, "compiti", f"{prof.name} ha provato {massimo} volte l'esercizio "
                                      f"«{e['testo']}» senza riuscirci: gli ho spiegato la "
                                      f"soluzione. Forse puoi aiutarlo a ripassarlo.",
                     registry=getattr(ctx, "speakers", None))
        except Exception as ex:  # noqa: BLE001
            print(f"   [MINORI] avviso non mandato: {type(ex).__name__}", flush=True)
    note_rule(ctx, "compiti_soluzione")
    chi_t = [u.name for u in M.tutori(prof, getattr(ctx, "speakers", None)) if u.name]
    a_chi = (" e ".join(("ad " if n[:1].lower() in "aeiou" else "a ") + n for n in chi_t[:2])
             or "a un adulto")
    o = "a" if getattr(prof, "gender", None) == "f" else "o"
    frase = (f"Hai provato {massimo} volte e ti sei impegnat{o}: adesso ti spiego la soluzione, "
             f"e lo dico anche {a_chi}, così " + ("possono" if len(chi_t) > 1 else "può")
             + " aiutarti meglio.")
    out = {"ok": True, "giusta": False, "soluzione_permessa": True, "da_dire_prima": frase,
           "cosa_fare": "Di' prima la frase da_dire_prima così com'è, poi spiega la soluzione "
                        "passo per passo, in modo semplice."}
    if e.get("espressione"):
        v = _valuta(e["espressione"])
        if v is not None:
            from .builtin import _to_say
            out["soluzione"] = _to_say(v)
    return out


def calcola_in_compiti(ctx, espressione: str) -> dict | None:
    """`calcola` per un minore con un esercizio aperto (modalità compiti): il risultato non si
    dà; l'espressione diventa l'esercizio da controllare con la sua risposta. None = calcola
    come sempre."""
    prof = M.profilo(ctx)
    p = M.preset(prof) if prof is not None else None
    if p is None or p.get("compiti") != "guida":
        return None
    comp = M.compiti()
    if not comp.attiva(prof.id):
        return None
    note_rule(ctx, "compiti_calcola")
    e = comp.apri(prof.id, espressione, espressione)
    if e.get("spiegato"):
        return None
    return {"ok": True, "modalita_compiti": True, "esercizio": e["testo"],
            "risultato": "nascosto: è un compito",
            "cosa_fare": "Siamo nei compiti: non dire il risultato. Chiedigli quanto gli viene e "
                         "controlla la sua risposta con compiti_aiuto (espressione e risposta)."}


# ─────────────────────────── minore_gestisci ───────────────────────────

AZIONI = ["stato", "imposta", "orari", "abilita_estensione", "togli_estensione", "autorizza",
          "nascita", "tutori", "riepilogo_compiti", "tempo_extra", "richieste",
          "approva_richiesta", "nega_richiesta"]


def _minuti(valore, predefinito: int = 30) -> int | None:
    """«30», «mezz'ora», «un'ora», «un quarto d'ora», «20 minuti» → minuti (None se non si
    capisce)."""
    import re
    t = str(valore or "").strip().lower()
    if not t:
        return predefinito
    if "mezz" in t:
        return 30
    if "quarto" in t:
        return 15
    m = re.search(r"\d+(?:[.,]\d+)?", t)
    if m:
        n = float(m.group(0).replace(",", "."))
        return int(round(n * 60 if re.search(r"\bor[ae]\b", t) else n))
    if re.search(r"\bun'?\s*ora\b", t):
        return 60
    return None


def _voce_sicura(ctx) -> bool:
    sc = getattr(ctx, "speaker_ctx", None)
    return getattr(sc, "identified_by", None) == "voce" or bool(getattr(sc, "sfida_superata",
                                                                       False))


def _richieste(ctx, chi, azione: str, nome: str, valore: str) -> dict:
    """Le richieste dei ragazzi in attesa (05/10, minori.Richieste): elencarle, approvarle,
    negarle. Decide solo un tutore del ragazzo (o chi amministra se non ne ha), con la voce
    riconosciuta in questa frase: mai una frase breve, mai lo scritto."""
    rq = M.richieste()
    speakers = getattr(ctx, "speakers", None)
    if rq is None:
        return _final("Le richieste dei ragazzi qui non ci sono.", ok=False, fatto=NIENTE)
    if chi is None or M.e_minore(chi):
        return _final("Le richieste dei ragazzi le decide un loro tutore.", ok=False,
                      fatto=NIENTE)
    attese = rq.in_attesa_per(chi, speakers)
    if azione == "richieste":
        if not attese:
            return _final("Non ci sono richieste dei ragazzi in attesa.")
        nomi = {getattr(u, "id", None): u.name for u in getattr(speakers, "users", {}).values()}
        frasi = [f"R{r['id']}: " + rq.frase(r, nomi.get(r["minore"], "un ragazzo"))
                 for r in attese[:4]]
        return _final(("Una richiesta: " if len(attese) == 1 else
                       f"{len(attese)} richieste: ") + "; ".join(frasi) + ".")
    if not _voce_sicura(ctx):
        sfida = serve_conferma(ctx, "minore_gestisci",
                               {"nome": nome, "azione": azione, "valore": valore},
                               "decidere la richiesta")
        if sfida is not None:
            return sfida
        note_rule(ctx, "minore_richiesta_voce")
        return _final("Per decidere una richiesta di un ragazzo devo riconoscere la tua voce: "
                      "dimmelo con una frase un po' più lunga.", ok=False, fatto=NIENTE)
    import re
    rid = None
    m = re.search(r"\d+", str(valore or ""))
    if m:
        rid = int(m.group(0))
    elif str(nome or "").strip() and speakers is not None:
        t = speakers.find(nome)
        u = speakers.get(t) if t else None
        mie = [r for r in attese if u is not None and r["minore"] == getattr(u, "id", None)]
        if len(mie) == 1:
            rid = mie[0]["id"]
    elif len(attese) == 1:
        rid = attese[0]["id"]
    if rid is None:
        return {"ok": False, "fatto": NIENTE, "errore": "quale richiesta?",
                "cosa_fare": "chiedi quale richiesta (o chiama con azione=richieste)"}
    minuti = _minuti(valore.split(None, 1)[1] if len(str(valore or "").split()) > 1 else "",
                     0) or None
    try:
        frase = rq.decidi(rid, azione == "approva_richiesta", chi, speakers, minuti=minuti)
    except PermissionError as e:
        note_rule(ctx, "minore_richiesta_altrui")
        return _final(f"Non posso: {e}.", ok=False, fatto=NIENTE)
    except ValueError as e:
        return _final(f"Non l'ho fatto: {e}.", ok=False, fatto=NIENTE)
    note_rule(ctx, "minore_richiesta_" + ("approvata" if azione == "approva_richiesta"
                                          else "negata"))
    return _final(frase)


def _tempo_extra(ctx, chi, minore, valore: str) -> dict:
    """«Oggi Bianca può giocare mezz'ora in più» (05/10): un adulto riconosciuto dalla voce,
    per quel minore e per oggi. Se non è un suo tutore resta scritto chi l'ha concesso (e i
    tutori lo sanno)."""
    if chi is None or M.e_minore(chi):
        note_rule(ctx, "gioco_tempo_extra_permesso")
        return _final("Il tempo di gioco in più lo dà un adulto.", ok=False, fatto=NIENTE)
    if not _voce_sicura(ctx):
        note_rule(ctx, "gioco_tempo_extra_voce")
        return _final("Per dare tempo di gioco in più devo riconoscere la tua voce: dimmelo con "
                      "una frase un po' più lunga.", ok=False, fatto=NIENTE)
    minuti = _minuti(valore, 30)
    if not minuti or not 1 <= minuti <= 240:
        return _final("Dimmi quanti minuti in più, per esempio mezz'ora.", ok=False,
                      fatto=NIENTE)
    tg = M.tempo_gioco()
    if tg is None:
        return _final("Il tempo di gioco qui non si può salvare.", ok=False, fatto=NIENTE)
    tutore = M.e_tutore(chi, minore)
    tg.concedi(minore, minuti, chi, tutore)
    note_rule(ctx, "gioco_tempo_extra" if tutore else "gioco_tempo_extra_non_tutore")
    print(f"   [MINORI] {chi.name} concede {minuti} minuti di gioco in più a {minore.name}"
          + ("" if tutore else " (non è un suo tutore)"), flush=True)
    frase = f"Va bene: oggi {minore.name} ha {M.minuti_detti(minuti)} di gioco in più."
    if not tutore:
        av = M.avvisi()
        if av is not None:
            try:
                av.manda(minore, "gioco", f"{chi.name} ha dato a {minore.name} "
                                          f"{M.minuti_detti(minuti)} di gioco in più per oggi.",
                         registry=getattr(ctx, "speakers", None))
            except Exception:  # noqa: BLE001
                pass
        frase += " Lo dico anche ai suoi tutori."
    return _final(frase)


# Le azioni di minore_gestisci che, chieste da un ragazzo per sé, sono una richiesta al tutore:
# azione → f(valore) = (cosa, nome, minuti) per richiesta_tutore
_A_RICHIESTA = {
    "tempo_extra": lambda v: ("tempo_gioco", "", v or None),
    "autorizza": lambda v: ("agenti", "", None),
    "abilita_estensione": lambda v: ("estensione", v, None),
    "orari": lambda v: ("orari", "", None),
}


def _minore_gestisci(ctx: ToolContext, nome: str = "", azione: str = "stato",
                     valore: str = "") -> dict:
    speakers = getattr(ctx, "speakers", None)
    chi = M.profilo(ctx)
    azione = str(azione or "stato").strip().lower()
    if azione in ("richieste", "approva_richiesta", "nega_richiesta"):
        return _richieste(ctx, chi, azione, str(nome or ""), str(valore or ""))
    trovato = speakers.find(nome) if (speakers is not None and str(nome or "").strip()) else None
    minore = speakers.get(trovato) if trovato else (chi if chi is not None and M.e_minore(chi)
                                                    else None)
    if minore is None or (not M.e_minore(minore) and azione not in ("nascita",)):
        return {"ok": False, "fatto": NIENTE, "errore": "non trovo un profilo minorenne con "
                "quel nome", "cosa_fare": "chiedi di chi si tratta; per registrarne uno nuovo "
                "usa registra_utente con la data di nascita"}
    tutore = M.e_tutore(chi, minore) or bool(getattr(chi, "admin", False))
    # Un ragazzo che chiede per sé un permesso («posso giocare mezz'ora in più?»): il modello
    # sceglieva a volte minore_gestisci (e2e del 06/10, 2 volte su 3) e la risposta era un
    # rifiuto. È la richiesta al tutore: la si crea (regola minore_gestisci_richiesta)
    if (chi is not None and M.e_minore(chi) and getattr(chi, "id", None) == minore.id
            and azione in _A_RICHIESTA):
        cosa, nome_r, minuti = _A_RICHIESTA[azione](str(valore or ""))
        note_rule(ctx, "minore_gestisci_richiesta")
        return _richiesta_tutore(ctx, cosa=cosa, nome=nome_r, minuti=minuti)
    if azione == "tempo_extra":
        return _tempo_extra(ctx, chi, minore, str(valore or ""))
    if azione == "stato":
        if chi is None or (chi.id != minore.id and not tutore):
            return _final("Le impostazioni di un ragazzo le può sentire lui o un suo tutore.",
                          ok=False, fatto=NIENTE)
        p = M.preset(minore)
        orari = ", ".join(p.get("orari") or []) or "nessuno"
        frase = (f"{minore.name}: fascia {p['fascia']}"
                 + (f", {p['eta']} anni" if p.get("eta") is not None else "")
                 + f". Internet: {p['internet']}; agenti: {p['agenti']}; casa: {p['casa']}; "
                   f"computer: {p['pc']}; documenti: {p['documenti']}; compiti: "
                   f"{p['compiti']}; orari di pausa: {orari}; estensioni: "
                   f"{', '.join(p.get('estensioni') or []) or 'nessuna'}; gioco al giorno: "
                   f"{M.minuti_detti(p.get('gioco_minuti') or 0)}")
        resta = M.gioco_restante_s(minore)
        if resta is not None:
            frase += f", oggi ne restano {M.minuti_detti(max(0, resta) / 60)}"
        frase += "."
        return _final(frase)
    if azione == "riepilogo_compiti":
        if not tutore:
            return _final("Il riepilogo dei compiti lo può sentire solo un tutore.", ok=False,
                          fatto=NIENTE)
        av = M.avvisi()
        frase = (av.riepilogo(minore) if av is not None else
                 "Il riepilogo dei compiti qui non c'è.")
        # Con gli esercizi del giorno (08/10, calliope/esercizi/): solo la frase, il dettaglio
        # con esercizi azione=riepilogo
        from ..esercizi import sessione as _S
        srv = _S.servizio()
        if srv is not None:
            try:
                r = srv.registro.riepilogo(minore.id, minore.name)
                if r["righe"]:
                    frase += " " + r["frase"]
            except Exception:  # noqa: BLE001 — il riepilogo dei compiti resta
                pass
        return _final(frase)
    # Cambiare: solo un tutore o chi amministra, riconosciuto dalla voce in questa frase
    if not tutore:
        note_rule(ctx, "minore_gestisci_permesso")
        return _final(f"Le regole di {minore.name} le può cambiare solo un suo tutore o chi "
                      f"amministra.", ok=False, fatto=NIENTE)
    sc = getattr(ctx, "speaker_ctx", None)
    if getattr(sc, "identified_by", None) not in ("voce",) and not getattr(sc, "sfida_superata",
                                                                          False):
        sfida = serve_conferma(ctx, "minore_gestisci",
                               {"nome": minore.name, "azione": azione, "valore": valore},
                               f"cambiare le regole di {minore.name}")
        if sfida is not None:
            return sfida
        note_rule(ctx, "minore_gestisci_voce")
        return _final("Per cambiare le regole di un ragazzo devo riconoscere la tua voce: "
                      "dimmelo con una frase un po' più lunga.", ok=False, fatto=NIENTE)
    reg = M.regole()
    if reg is None and azione not in ("nascita", "tutori"):
        return _final("Le regole dei ragazzi qui non si possono salvare.", ok=False,
                      fatto=NIENTE)
    f = M.fascia(minore)
    try:
        if azione == "imposta":
            k, _, v = str(valore or "").partition("=")
            if not v:
                k, _, v = str(valore or "").partition(" ")
            k = k.strip().lower()
            reg.imposta(minore.id, k, M.controlla_valore(k, v, f))
            frase = f"Fatto: per {minore.name} {k} adesso è {M.preset(minore).get(k)}."
        elif azione == "orari":
            v = M.controlla_valore("orari", valore, f)
            reg.imposta(minore.id, "orari", v or None)
            frase = (f"Fatto: con {minore.name} non parlo {', '.join('dalle ' + o.replace('-', ' alle ') for o in v)}."
                     if v else f"Fatto: per {minore.name} nessun orario di pausa.")
        elif azione in ("abilita_estensione", "togli_estensione"):
            attuali = set(reg.leggi(minore.id).get("estensioni") or [])
            n = M.controlla_valore("estensioni", valore, f)
            attuali = attuali | set(n) if azione == "abilita_estensione" else attuali - set(n)
            reg.imposta(minore.id, "estensioni", sorted(attuali))
            frase = (f"Fatto: {minore.name} può usare {', '.join(sorted(attuali))}." if attuali
                     else f"Fatto: {minore.name} non ha estensioni abilitate.")
        elif azione == "autorizza":
            parti = str(valore or "").split()
            cosa = (parti[0] if parti else "agenti").lower()
            minuti = float(next((x for x in parti[1:] if x.replace(".", "").isdigit()), 60))
            reg.autorizza(minore.id, cosa, minuti, getattr(chi, "id", "?"))
            frase = (f"Va bene: per i prossimi {int(minuti)} minuti {minore.name} può usare "
                     f"{'l agente' if cosa == 'agenti' else cosa}.").replace("l agente", "l'agente")
        elif azione == "nascita":
            d = M.leggi_data(valore)
            if d is None:
                raise ValueError("non ho capito la data: dimmela come «12 maggio 2017»")
            minore.nascita, minore.fascia = d.isoformat(), None
            speakers.save()
            nuova = M.fascia(minore)
            frase = (f"Fatto: {minore.name} è nato il {d.day} {MESI[d.month - 1]} {d.year}, "
                     + (f"fascia {nuova}." if nuova else "quindi è maggiorenne."))
        elif azione == "tutori":
            import re
            ids = []
            for n in re.split(r",|\se\s", str(valore or "")):
                t = speakers.find(n.strip()) if n.strip() else None
                if t:
                    ids.append(speakers.get(t).id)
            if not ids:
                raise ValueError("non trovo quei nomi tra le persone registrate")
            minore.tutori = list(dict.fromkeys(ids))
            speakers.save()
            frase = f"Fatto: i tutori di {minore.name} adesso sono " + ", ".join(
                u.name for u in speakers.users.values() if u.id in minore.tutori) + "."
        else:
            return {"ok": False, "errore": f"azione sconosciuta: {azione}", "azioni": AZIONI}
    except ValueError as e:
        return _final(f"Non l'ho cambiato: {e}.", ok=False, fatto=NIENTE)
    note_rule(ctx, "minore_regole_cambiate")
    print(f"   [MINORI] {getattr(chi, 'name', '?')} cambia {azione} di {minore.name}", flush=True)
    return _final(frase)


def _richiesta_tutore(ctx: ToolContext, cosa: str = "", nome: str = "", minuti=None) -> dict:
    """Un minore chiede qualcosa al tutore (05/10): un gioco o un'estensione, l'agente, più
    tempo di gioco, un'eccezione agli orari. La richiesta resta in sospeso finché il tutore non
    decide (minori.Richieste)."""
    prof = M.profilo(ctx)
    if prof is None or not M.e_minore(prof):
        return {"ok": False, "fatto": "non serve: chi parla non è un ragazzo con le regole dei "
                                      "minori", "cosa_fare": "rispondi normalmente"}
    rq = M.richieste()
    if rq is None:
        return _final("Adesso non posso chiederlo: chiedilo tu a un adulto.", ok=False,
                      fatto=NIENTE)
    cosa = str(cosa or "").strip().lower()
    tipo = {"gioco": "estensione", "estensione": "estensione", "agenti": "agenti",
            "agente": "agenti", "tempo_gioco": "tempo_gioco", "tempo": "tempo_gioco",
            "orari": "orari", "pausa": "orari"}.get(cosa)
    if tipo is None:
        return {"ok": False, "errore": "cosa: gioco, estensione, agenti, tempo_gioco o orari"}
    oggetto = cosa
    if tipo == "estensione":
        from ..minori import _norm
        oggetto = _norm(nome).replace(" ", "_").removeprefix("est_")
        if not oggetto:
            return {"ok": False, "errore": "manca il nome del gioco o della funzione",
                    "cosa_fare": "chiedi quale"}
        if M.estensione_consentita(prof, oggetto):
            return _final("Questo puoi già usarlo: chiedimelo pure.")
    m = _minuti(minuti, 0) if minuti not in (None, "") else None
    rid, nuova = rq.crea(prof, tipo, oggetto, minuti=m, registry=getattr(ctx, "speakers", None))
    note_rule(ctx, "minore_richiesta_tutore")
    t = M._tutore_nome(prof, getattr(ctx, "speakers", None))
    return _final(f"L'ho chiesto a {t}: ti dico appena risponde." if nuova else
                  f"L'ho già chiesto a {t}: aspettiamo la risposta.", richiesta=f"R{rid}")


def minori_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="richiesta_tutore",
            description=("Solo se chi parla è minorenne (dati del turno) e chiede di poter "
                         "fare una cosa che serve il permesso di un adulto: un gioco o una "
                         "funzione nuova (nome), l'agente, più tempo di gioco («posso giocare "
                         "mezz'ora in più?»: tempo_gioco) o di restare sveglio oltre la pausa. "
                         "La chiedo io al suo tutore. minuti: se li dice."),
            parameters={"type": "object", "properties": {
                "cosa": {"type": "string", "enum": ["gioco", "estensione", "agenti",
                                                    "tempo_gioco", "orari"]},
                "nome": {"type": "string"}, "minuti": {"type": "string"}},
                "required": ["cosa"]},
            func=_richiesta_tutore, risk="azione", levels=FAMILY),
        ToolSpec(
            name="compiti_aiuto",
            description=("Solo se nei dati del turno c'è «compiti: guida» e chi parla chiede "
                         "aiuto per un compito di scuola: registra l'esercizio e controlla la "
                         "sua risposta, senza mai dargli la soluzione prima che il tool lo "
                         "permetta. Richiamalo a ogni risposta che dice (con risposta), anche "
                         "nei turni dopo. esercizio: in breve; espressione: per i conti, come per "
                         "calcola; risposta: quella detta da lui; giusta: per gli esercizi senza "
                         "conti, true o false secondo te."),
            parameters={"type": "object", "properties": {
                "esercizio": {"type": "string"}, "espressione": {"type": "string"},
                "risposta": {"type": "string"}, "giusta": {"type": "boolean"}},
                "required": ["esercizio"]},
            func=_compiti_aiuto, risk="lettura", levels=FAMILY),
        ToolSpec(
            name="minore_gestisci",
            description=("Per gli adulti: le regole di un figlio o di un ragazzo di casa "
                         "(se chi parla è un ragazzo e chiede un permesso per sé, è "
                         "richiesta_tutore). «X mi ha chiesto qualcosa?», «ci sono richieste dei "
                         "ragazzi?»: richieste. Azioni: stato; imposta "
                         "(valore «internet=no», «gioco_minuti=45»…); orari in cui Calliope "
                         "non gli risponde (valore «21:00-07:30», «nessuno»); abilita_estensione "
                         "o togli_estensione; autorizza (valore «agenti 60»: per un'ora); "
                         "tempo_extra (oggi può giocare di più: valore «30»); richieste, "
                         "approva_richiesta o nega_richiesta (valore «R3»); nascita; tutori; "
                         "riepilogo_compiti. nome: di chi."),
            parameters={"type": "object", "properties": {
                "nome": {"type": "string"},
                "azione": {"type": "string", "enum": AZIONI},
                "valore": {"type": "string"}}, "required": ["azione"]},
            func=_minore_gestisci, risk="azione", levels=FAMILY),
        # Esercizi generati da Calliope (08/10, calliope/esercizi/, tools/esercizi.py)
        _esercizi_spec(),
    ]


def _esercizi_spec() -> ToolSpec:
    from .esercizi import esercizi_spec
    return esercizi_spec()
