"""
Le proiezioni: funzioni pure degli eventi (10/10/2026, § 3 del progetto
docs/ricerche/2026-10-10-registro-eventi.md).

`(eventi, forma) → vista`, senza stato nascosto: niente orologio, niente caso, niente Brain né
ciclo; le eccezioni stanno negli eventi (un turno escluso, un esito riservato), non qui. Stessi
eventi, stessi byte (chiavi JSON ordinate dove serve). Tetto di 600 righe per questo file
(`prova_eventi_pure`): si alza solo scrivendo il motivo nel progetto (§ 10, punto 2).

Passo 1 (in ombra): la proiezione del contesto si confronta a ogni turno con la storia di Brain
(calliope/eventi/ombra.py). Passo 3 (`eventi: attivo`): Brain legge da qui i messaggi dei turni
chiusi (`messaggi(…, per_risposta=True)`): la forma che la risposta dopo deve vedere, con i
risultati sigillati dai campi dell'evento (riservato, personale, non fidato: decisi alla
scrittura), senza i `cosa_fare` (promemoria del blocco dello stato, non storia), e solo
l'argomento corrente per intero (§ 13: gli altri nell'`indice`). In più i promemoria non parlati:
la parte non detta di una risposta interrotta (§ 11.4), i `cosa_fare` del turno prima.

Solo libreria standard e calliope.eventi.tipi.
"""
from __future__ import annotations

import dataclasses
import json

from .tipi import TIPI, TRACCIA_PRIVATA, Evento, atti_di, sigillato


class Escluso(str):
    """Una riga di PROIEZIONE_CONTESTO: il tipo non entra nel contesto, e perché."""


def ESCLUSO(motivo: str) -> Escluso:  # noqa: N802 — si legge come una parola della tabella
    return Escluso(motivo)


# Ogni tipo ha la sua riga: come si rende nel contesto del modello, o ESCLUSO e perché (§ 3.1)
PROIEZIONE_CONTESTO: dict[str, str] = {
    "conversazione_aperta": "il riassunto di ripresa o la coda, come messaggio di sistema "
                            "subito dopo il prompt",
    "conversazione_chiusa": ESCLUSO("chiude il segmento: la proiezione è del segmento aperto"),
    "detto_persona": "il messaggio della persona (la trascrizione, o «dopo» della trascrizione "
                     "capita accettata), con gli ingressi del turno davanti",
    "trascrizione_capita": "cambia il testo del detto_persona del suo turno, se accettata",
    "dato_in_ingresso": "davanti al messaggio della persona del suo turno (la busta), con la "
                        "traccia della fonte",
    "foto_in_ingresso": "davanti al messaggio della persona del suo turno (l'etichetta), con i "
                        "numeri dell'album",
    "allegato_in_ingresso": "i numeri e la traccia della fonte sul messaggio della persona",
    "dati_del_turno": ESCLUSO("effimeri: blocco dello stato e dati del turno, mai storia"),
    "passata_modello": ESCLUSO("visibilità registro: rigioco, diagnosi e la parte non detta di "
                               "una risposta interrotta (promemoria del blocco dello stato)"),
    "chiamata_tool": "messaggio dell'assistente con le chiamate",
    "esito_tool": "messaggio del tool: sigillato dai suoi campi, forma viva nel turno e nel "
                  "precedente, definitiva prima",
    "detto_calliope": "testo dell'assistente se sentito (fino a voce_fine), atti fuori "
                      "conversazione esclusi (ATTI_FUORI)",
    "voce_fine": "quali frasi si sono sentite; un'interruzione mette il segno in fondo",
    "interruzione": ESCLUSO("il segno lo mette voce_fine"),
    "proposta_aperta": ESCLUSO("stato della macchina: va nel blocco dello stato, non nella "
                               "storia"),
    "proposta_chiusa": ESCLUSO("stato della macchina"),
    "sfida_chiesta": ESCLUSO("stato della sfida; le parole mai"),
    "sfida_esito": ESCLUSO("stato della sfida"),
    "modulo_compilato": "il messaggio della persona «(Ho scritto sullo schermo i dati …)», "
                        "solo i nomi dei campi",
    "turno_escluso": "toglie dalla proiezione tutto il suo turno",
    "compressione": "il riassunto come messaggio di sistema; i turni fino a fino_a escono",
    "scheda_mandata": ESCLUSO("il contenuto è della cronologia degli schermi"),
    "turno_riassegnato": "toglie il turno dal registro d'origine",
    "turno_chiuso": ESCLUSO("sorgente del registro dei turni"),
    "argomento_nuovo": "da qui i turni sono dell'argomento nuovo: per intero solo quelli "
                       "dell'argomento corrente, gli altri nell'indice (§ 13)",
    "argomento_ripreso": "l'argomento torna corrente: i suoi turni di nuovo per intero",
}

# E nel registro dei turni (passo 5: oggi `TurnLog` riceve la riga dal ciclo): il campo di oggi
# che il tipo diventerà, o ESCLUSO
PROIEZIONE_TURNI: dict[str, str] = {
    "conversazione_aperta": "conversazione.come",
    "conversazione_chiusa": "conversazione_nuova / regole conversazione_*",
    "detto_persona": "testo, richiesta, livello, canale (stessa privacy di oggi)",
    "trascrizione_capita": "stt_capito",
    "dato_in_ingresso": "allegati (solo tipo e dimensione)",
    "foto_in_ingresso": "foto (solo numeri)",
    "allegato_in_ingresso": "allegati",
    "dati_del_turno": ESCLUSO("solo nomi e lunghezze, nel rigioco"),
    "passata_modello": "tool, regole (spinte), generati",
    "chiamata_tool": "tool[].nome, argomenti (mai per gli ospiti)",
    "esito_tool": "tool[].ok",
    "detto_calliope": "risposta_inviata",
    "voce_fine": "risposta (frasi sentite), interrotta",
    "interruzione": "interruzione",
    "proposta_aperta": "dialogo_ombra.proposta",
    "proposta_chiusa": "dialogo_ombra, regole sospeso_*",
    "sfida_chiesta": "regole sfida_voce",
    "sfida_esito": "regole sfida_risposta",
    "modulo_compilato": "modulo, campi",
    "turno_escluso": "esito non_rivolta",
    "compressione": "compressione",
    "scheda_mandata": ESCLUSO("schede: registro degli schermi"),
    "turno_riassegnato": "conversazione (riga nuova)",
    "turno_chiuso": "la riga del turno: esito, regole, tempi, contesto",
    "argomento_nuovo": "regole argomento_nuovo, argomento",
    "argomento_ripreso": "regole argomento_ripreso, argomento",
}

# Atti di Calliope che non entrano nella conversazione del modello: frasi d'attesa (decisione di
# Dario del 10/10, § 4.2), saluto all'avvio e frasi dei giochi (fuori conversazione, § 1.1),
# chiusure («A presto!»: vanno nel segmento che si chiude, mai nel contesto di uno aperto). La
# categoria «voluto» dell'elenco chiuso degli atti (tipi.ATTI, passo 2)
ATTI_FUORI = atti_di("voluto")

# Il segno d'interruzione (§ 8.1 punto 6, scelto al passo 3): quello di oggi, che il modello
# conosce dal 26/09; l'unica annotazione non detta del contesto, chiusa
SEGNO_INTERROTTA = " … (interrotta)"
TESTO_INTERROTTA_VUOTA = "… (interrotta)"
# Tetto dei promemoria non parlati (caratteri)
PROMEMORIA_MAX = 400
ARGOMENTO_0 = "a0"                    # l'argomento d'inizio, senza titolo


@dataclasses.dataclass(frozen=True)
class Forma:
    """La forma dei turni chiusi (§ 5): i numeri di Brain di oggi (`OLD_RESULT_CHARS`,
    `_OLD_TRACE`, `_OLD_TIME`, `WEB_TOLTO`, `_PRIVATE_TRACE`), passati da chi chiama: la
    proiezione non importa Brain. `web_tolto` vuoto: il risultato non fidato resta com'è."""
    risultato_max: int = 400
    traccia: str = "risultato di un turno precedente: la risposta che lo usava è nella storia"
    ora_di_allora: tuple = ()
    web_tolto: str = ""
    traccia_privata: str = TRACCIA_PRIVATA
    # Le forme ridotte di alcuni tool nei turni vecchi (13/10, le notizie: titoli e testate in
    # busta, calliope/notizie/contesto.py): ((nome, funzione(contenuto) → testo o None), …)
    riduzioni: tuple = ()


FORMA = Forma()


def modulo_testo(titolo, campi) -> str:
    nomi = ", ".join(str(c).lower() for c in campi or ())
    if titolo:
        return f"(Ho scritto sullo schermo i dati per «{titolo}»: {nomi}.)"
    return f"(Ho scritto sullo schermo i dati: {nomi}.)"


def _nuovo_turno(chiave: int, persona, turno: int, argomento: str) -> dict:
    return {"chiave": chiave, "persona": persona, "ingressi": "", "brain": False,
            "canale": None, "chiamate": [], "esiti": [], "inviate": [], "sentite": set(),
            "interrotta": False, "escluso": False, "turno": turno, "modulo": False,
            "capito": False, "esito": None, "argomento": argomento, "fonti": set(),
            "fonti_detto": set(), "img": [], "all": [], "all_info": [], "generato": []}


def _fonti(x) -> set:
    return {f for f in str(x or "").split(",") if f and f != "busta"}


# I tipi che non sono «modello» ma servono alla vista (struttura, promemoria)
_STRUTTURA = frozenset({"voce_fine", "turno_escluso", "turno_riassegnato", "conversazione_aperta",
                        "turno_chiuso", "passata_modello"})


def turni(eventi, da: int | None = None) -> dict:
    """La conversazione del segmento divisa in turni: {"riassunto", "turni": [...],
    "argomenti": [...], "corrente"}. Un turno comincia con un detto_persona (o un modulo); gli
    annunci prima di ogni domanda sono un turno senza persona (chiave = seq del primo evento).
    `da`: la finestra, cioè il seq del primo turno che entra (il taglio in testa deciso dal
    conto dei token, § 3.1). Ogni turno ha il suo argomento (§ 13)."""
    riassunto = None
    fino_a = 0
    out: list[dict] = []
    per_chiave: dict[int, dict] = {}
    cur = None
    arg = ARGOMENTO_0
    argomenti: dict[str, dict] = {ARGOMENTO_0: {"id": ARGOMENTO_0, "titolo": None, "ora": None,
                                                "lasciato": []}}
    for e in eventi:
        tipo, d = e.tipo, e.dati
        if e.vis not in ("modello", "turno") and tipo not in _STRUTTURA:
            continue
        if tipo == "conversazione_aperta":
            if d.get("riassunto"):
                riassunto = str(d["riassunto"])
        elif tipo == "compressione":
            if d.get("riassunto"):
                riassunto = str(d["riassunto"])
            fino_a = max(fino_a, int(d.get("fino_a") or 0))
        elif tipo in ("argomento_nuovo", "argomento_ripreso"):
            ident = str(d.get("id") or f"a{e.seq}")
            if arg in argomenti:
                lasciato = list(d.get("da_parte") or ())
                argomenti[arg]["lasciato"] = lasciato
                if not argomenti[arg].get("titolo"):
                    # Un argomento senza titolo (quello d'inizio) prende quello di ciò che ha
                    # lasciato aperto (lo sviluppo)
                    argomenti[arg]["titolo"] = next(
                        (x.get("titolo") for x in lasciato if isinstance(x, dict)
                         and x.get("titolo")), None)
            a = argomenti.setdefault(ident, {"id": ident, "titolo": d.get("titolo"),
                                             "ora": d.get("ora"), "lasciato": []})
            a["lasciato"] = []
            if d.get("titolo"):
                a["titolo"] = d.get("titolo")
            # L'ordine: l'ultimo toccato in fondo (l'indice va dal più recente)
            argomenti[ident] = argomenti.pop(ident)
            arg = ident
            if cur is not None and cur["turno"] == e.turno:
                cur["argomento"] = arg          # il turno che ha cambiato è del nuovo
        elif tipo == "detto_persona" or tipo == "modulo_compilato":
            persona = (str(d.get("testo") or "") if tipo == "detto_persona"
                       else modulo_testo(d.get("titolo"), d.get("campi")))
            cur = _nuovo_turno(e.seq, persona, e.turno, arg)
            cur["brain"] = bool(d.get("brain"))
            cur["canale"] = d.get("canale") or ("modulo" if tipo == "modulo_compilato"
                                                else None)
            cur["modulo"] = tipo == "modulo_compilato"
            out.append(cur)
            per_chiave[e.seq] = cur
        elif cur is None and tipo in ("detto_calliope", "chiamata_tool", "esito_tool",
                                      "voce_fine"):
            cur = _nuovo_turno(e.seq, None, e.turno, arg)
            out.append(cur)
            per_chiave[e.seq] = cur
        if cur is None:
            continue
        if tipo == "trascrizione_capita" and d.get("accettata") and d.get("dopo"):
            cur["persona"], cur["capito"] = str(d["dopo"]), True
        elif tipo in ("dato_in_ingresso", "foto_in_ingresso", "allegato_in_ingresso"):
            cur["ingressi"] += str(d.get("testo") or "")
            cur["fonti"] |= _fonti(d.get("fonte"))
            if tipo == "foto_in_ingresso":
                cur["img"] += [n for n in d.get("numeri") or () if isinstance(n, int)]
            elif tipo == "allegato_in_ingresso":
                cur["all"] += [n for n in d.get("numeri") or () if isinstance(n, int)]
                cur["all_info"] += [str(x) for x in d.get("info") or ()]
        elif tipo == "chiamata_tool":
            cur["chiamate"].append({"id": d.get("id"), "name": d.get("nome"),
                                    "arguments": d.get("argomenti") or {},
                                    "_passata": d.get("passata")})
        elif tipo == "esito_tool":
            cur["esiti"].append({"id": d.get("id"), "name": d.get("nome"),
                                 "content": str(d.get("contenuto") or ""),
                                 **{k: d.get(k) for k in ("riservato", "personale",
                                                          "non_fidato", "fonte", "resta")}})
        elif tipo == "detto_calliope":
            cur["inviate"].append((int(d.get("frase") or 0), str(d.get("testo") or ""),
                                   d.get("atto"), d.get("autore"), d.get("canale"),
                                   d.get("dopo_chiamate")))
            if d.get("fonte") and d.get("atto") not in ATTI_FUORI:
                cur["fonti_detto"] |= _fonti(d.get("fonte"))
        elif tipo == "voce_fine":
            da_f, n = int(d.get("da") or 0), int(d.get("sentite") or 0)
            cur["sentite"].update(range(da_f, da_f + n))
            if d.get("interrotta"):
                cur["interrotta"] = True
        elif tipo == "passata_modello":
            if isinstance(d.get("testo"), str):
                cur["generato"].append(d["testo"])
        elif tipo == "turno_chiuso":
            cur["esito"] = d.get("esito")
        elif tipo == "turno_escluso":
            t = per_chiave.get(int(d.get("escluso") or 0))
            if t is not None:
                t["escluso"] = True
        elif tipo == "turno_riassegnato":
            t = per_chiave.get(int(d.get("seq") or 0))
            if t is not None:
                t["escluso"] = True
    tenuti = [t for t in out if not t["escluso"] and t["chiave"] > fino_a
              and (da is None or t["chiave"] >= da)]
    return {"riassunto": riassunto, "turni": tenuti, "argomenti": list(argomenti.values()),
            "corrente": arg}


def detto(turno: dict) -> list[tuple]:
    """Le frasi sentite del turno che entrano nella conversazione: (testo, atto, autore,
    canale), nell'ordine."""
    return [(testo, atto, autore, canale) for frase, testo, atto, autore, canale, _c
            in turno["inviate"] if frase in turno["sentite"] and atto not in ATTI_FUORI
            and testo.strip()]


def _posizioni(turno: dict) -> list[tuple]:
    """Le frasi sentite con la loro posizione fra le chiamate (passo 2): (testo, quante chiamate
    c'erano già quando è partita; None = dopo tutte, come gli eventi del passo 1)."""
    return [(testo, c) for frase, testo, atto, _a, _can, c in turno["inviate"]
            if frase in turno["sentite"] and atto not in ATTI_FUORI and testo.strip()]


def _gruppi(chiamate: list[dict]) -> list[list[dict]]:
    """Le chiamate del turno per passata del modello (un messaggio dell'assistente per passata,
    come nella storia di Brain); senza la passata (eventi del passo 1) un gruppo solo."""
    gruppi: list[list[dict]] = []
    prima = object()
    for c in chiamate:
        p = c.get("_passata")
        if not gruppi or p is None or p != prima:
            if gruppi and p is None and prima is None:
                gruppi[-1].append(c)
                continue
            gruppi.append([])
        gruppi[-1].append(c)
        prima = p
    return gruppi


def testo_assistente(turno: dict) -> str:
    """Il testo dell'assistente del turno: le frasi sentite, e il segno se interrotto."""
    testo = " ".join(t for t, *_ in detto(turno)).strip()
    if turno["interrotta"]:
        return (testo + SEGNO_INTERROTTA) if testo else TESTO_INTERROTTA_VUOTA
    return testo


def _forma_esito(contenuto: str, nome, vecchio: bool, ora: bool, forma: Forma) -> str:
    """La forma definitiva di un risultato (come Brain._compact_old_results di oggi)."""
    try:
        res = json.loads(contenuto)
    except (ValueError, TypeError):
        res = None
    if ora and nome == "ora_attuale" and isinstance(res, dict) and "ora" in res:
        return json.dumps({"ora_di_allora": res["ora"], **dict(forma.ora_di_allora)},
                          ensure_ascii=False)
    if not vecchio or len(contenuto) <= forma.risultato_max:
        return contenuto
    for nome_r, riduci in forma.riduzioni:
        if nome == nome_r:
            # Le notizie dette (13/10): titoli e testate restano, in busta (come Brain)
            ridotto = riduci(contenuto)
            if ridotto is not None:
                return ridotto
    res = res if isinstance(res, dict) else {}
    ok = "errore" not in res and res.get("ok") is not False
    detta = ""
    for k in ("conferma", "risposta_finale", "da_dire"):
        v = res.get(k)
        if isinstance(v, str) and v.strip():
            detta = v.strip()
            break
    small = {"ok": ok, **({"conferma": detta} if detta else {"nota": forma.traccia})}
    if not ok and res.get("errore"):
        small["errore"] = res["errore"]
    return json.dumps(small, ensure_ascii=False)


def _senza_cosa_fare(contenuto: str) -> str:
    """Il risultato senza `cosa_fare` (passo 3: è un promemoria del blocco dello stato del
    turno dopo, non storia)."""
    try:
        res = json.loads(contenuto)
    except (ValueError, TypeError):
        return contenuto
    if not isinstance(res, dict) or "cosa_fare" not in res:
        return contenuto
    res.pop("cosa_fare")
    return json.dumps(res, ensure_ascii=False)


def _esito_reso(r: dict, vecchio: bool, ora: bool, forma: Forma, per_risposta: bool) -> str:
    """Il risultato come lo vede la risposta dopo la sua (sempre, nella proiezione: i turni
    proiettati sono chiusi): il testo dei siti tolto (`Brain._togli_non_fidati`), riservati e
    personali sigillati (`_seal_private`), poi la forma definitiva."""
    c = r["content"]
    if r.get("non_fidato") and forma.web_tolto and not r.get("resta"):
        c = forma.web_tolto
    c = sigillato(c, bool(r.get("riservato")), bool(r.get("personale")), forma.traccia_privata)
    if per_risposta:
        c = _senza_cosa_fare(c)
    return _forma_esito(c, r["name"], vecchio, ora, forma)


def _con_fonte(m: dict, fonti: set) -> dict:
    if fonti:
        m["_fonte"] = ",".join(sorted(fonti))
    return m


def messaggi(vista: dict, forma: Forma = FORMA, per_risposta: bool = False,
             seq: bool = False, riassunto: bool = True) -> list[dict]:
    """I messaggi di riassunto e storia per il modello (§ 3.1), nello stesso formato della storia
    di Brain di oggi (così i due backend non cambiano). Il prompt di sistema, il blocco dello
    stato, i dati del turno e le spinte li aggiunge chi chiama, dove sono oggi.

    `per_risposta` (passo 3): la forma per la risposta che sta per cominciare (il turno vivo è
    dopo l'ultimo proiettato), solo l'argomento corrente, senza `cosa_fare`, e un messaggio
    vuoto dell'assistente dopo una frase della persona senza niente di detto (uno stop: i ruoli
    si alternano, come vogliono alcuni modelli di chat). `seq`: ogni messaggio con `_seq`, la
    chiave del suo turno (per Brain: compressione, taglio, archivio). `riassunto`: il riassunto
    in testa (Brain lo mette da sé)."""
    out: list[dict] = []
    if riassunto and vista.get("riassunto"):
        out.append({"role": "system", "content": vista["riassunto"]})
    tt = vista["turni"]
    if per_risposta:
        corrente = vista.get("corrente", ARGOMENTO_0)
        tt = [t for t in tt if t.get("argomento", ARGOMENTO_0) == corrente]
    # Il turno di riferimento per la forma: l'ultimo passato dal modello (Brain compatta a ogni
    # sua risposta, non dopo una cortesia o uno stop); per la risposta che comincia, lei
    dal_modello = [i for i, t in enumerate(tt) if t["brain"]]
    rif = len(tt) if per_risposta else (dal_modello[-1] if dal_modello else None)
    for i, t in enumerate(tt):
        tag = {"_seq": t["chiave"]} if seq else {}
        if t["persona"] is not None:
            u = {"role": "user", "content": (t["ingressi"] + t["persona"]).strip(), **tag}
            if t["img"]:
                u["_img"] = list(t["img"])
            if t["all"]:
                u["_all"], u["_all_info"] = list(t["all"]), list(t["all_info"])
            out.append(_con_fonte(u, t["fonti"] | ({"foto"} if t["img"] else set())))
        if not t["chiamate"]:
            testo = testo_assistente(t)
            if testo or (per_risposta and t["persona"] is not None):
                out.append(_con_fonte({"role": "assistant", "content": testo, **tag},
                                      t["fonti_detto"]))
            continue
        # Le frasi nella posizione in cui sono state dette rispetto alle chiamate (passo 2:
        # `dopo_chiamate` dell'uscita unica): quelle partite prima di un gruppo di chiamate
        # sono il testo del messaggio con le chiamate, come nella storia di Brain
        vecchio = rif is not None and i < rif - 1
        ora = rif is not None and i < rif
        gruppi = _gruppi(t["chiamate"])
        fatti: list[int] = []
        for g in gruppi:
            fatti.append((fatti[-1] if fatti else 0) + len(g))
        pezzi: list[list[str]] = [[] for _ in range(len(gruppi) + 1)]
        for testo, c in _posizioni(t):
            k = len(gruppi) if c is None else sum(1 for f in fatti if f <= c)
            pezzi[k].append(testo)
        # Gli esiti in ordine, uno per chiamata (gli id si ripetono da una passata all'altra:
        # «call_0»); quelli in più dopo l'ultimo gruppo, come prima
        esiti = list(t["esiti"])
        for k, g in enumerate(gruppi):
            out.append({"role": "assistant", "content": " ".join(pezzi[k]).strip(),
                        "tool_calls": [{x: v for x, v in c.items() if x != "_passata"}
                                       for c in g], **tag})
            n = len(esiti) if k == len(gruppi) - 1 else len(g)
            for r in esiti[:n]:
                out.append(_con_fonte({"role": "tool", "tool_call_id": r["id"],
                                       "name": r["name"], **tag,
                                       "content": _esito_reso(r, vecchio, ora, forma,
                                                              per_risposta)},
                                      _fonti(r.get("fonte"))))
            esiti = esiti[n:]
        testo = " ".join(pezzi[-1]).strip()
        if t["interrotta"]:
            testo = (testo + SEGNO_INTERROTTA) if testo else TESTO_INTERROTTA_VUOTA
        if testo:
            out.append(_con_fonte({"role": "assistant", "content": testo, **tag},
                                  t["fonti_detto"]))
    return out


def contesto(eventi, forma: Forma = FORMA, da: int | None = None) -> list[dict]:
    """La proiezione del contesto del modello: `messaggi(turni(eventi))`."""
    return messaggi(turni(eventi, da), forma)


def _corto(t: str, n: int, coda: bool = False) -> str:
    t = " ".join(str(t or "").split())
    if len(t) <= n:
        return t
    return "…" + t[-(n - 1):].lstrip() if coda else t[:n - 1].rstrip() + "…"


# ─────────────────────────── promemoria non parlati (§ 4.3, § 11.4) ───────────────────────────
INTERROTTA_MSG = ("Promemoria (non detto): la tua risposta di prima è stata interrotta. Chi parla "
                  "ha sentito fino a «{sentito}»; non ha sentito: «{resto}». Se chiede di "
                  "ripetere o di continuare, quella è la parte che non ha sentito.")
COSA_FARE_MSG = "Promemoria dai risultati dei tool della tua ultima risposta: {cosa}"


def promemoria_interrotta(vista: dict, tetto: int = PROMEMORIA_MAX) -> str | None:
    """La parte non detta dell'ultima risposta interrotta (decisione di Dario del 10/10, § 11.4):
    le frasi mandate e non sentite e il resto generato dal modello. Solo se la risposta
    interrotta è l'ultima (o subito prima di uno stop senza risposta). None altrimenti."""
    for t in reversed(vista["turni"]):
        if t["persona"] is not None and not t["inviate"] and not t["chiamate"]:
            continue                             # lo stop, o una frase senza risposta
        if not t["interrotta"]:
            return None
        sentite = " ".join(x for x, *_ in detto(t)).strip()
        mandate = " ".join(testo for frase, testo, atto, *_ in t["inviate"]
                           if frase not in t["sentite"] and atto not in ATTI_FUORI)
        generato = " ".join(" ".join(t["generato"]).split())
        resto = mandate.strip()
        if generato:
            # Il testo generato dopo l'ultima frase sentita (la passata ne sa più della voce)
            i = generato.find(sentite[-40:]) if sentite else 0
            dopo = generato[i + len(sentite[-40:]):] if sentite and i >= 0 else generato
            if len(dopo.strip()) > len(resto):
                resto = dopo.strip()
        if not resto:
            return None
        return INTERROTTA_MSG.format(sentito=_corto(sentite, 120, coda=True) or "niente",
                                     resto=_corto(resto, tetto))
    return None


def promemoria_cosa_fare(vista: dict, tetto: int = PROMEMORIA_MAX) -> str | None:
    """I `cosa_fare` dei risultati dell'ultimo turno (passo 3: tolti dalla storia, valgono per
    il turno dopo nel blocco dello stato)."""
    tt = vista["turni"]
    if not tt:
        return None
    cose = []
    for r in tt[-1]["esiti"]:
        if r.get("riservato") or r.get("non_fidato"):
            continue
        try:
            res = json.loads(r["content"])
        except (ValueError, TypeError):
            continue
        c = res.get("cosa_fare") if isinstance(res, dict) else None
        if isinstance(c, str) and c.strip() and c.strip() not in cose:
            cose.append(c.strip())
    return COSA_FARE_MSG.format(cosa=_corto(" ".join(cose), tetto)) if cose else None


# ─────────────────────────── argomenti (§ 13) ───────────────────────────
INDICE_MSG = ("Argomenti di questa conversazione messi da parte (i loro scambi non sono qui "
              "sotto; se chi parla ci torna, chiama argomento con azione «riprendi» e il titolo): "
              "{voci}.")


def argomenti(vista: dict) -> dict:
    """Il fold degli argomenti: {"corrente": {id, titolo, ora}, "da_parte": [{id, titolo, ora,
    lasciato, ultimo}]} (dal più recente). `ultimo`: l'ultima frase sentita dell'argomento."""
    corrente = vista.get("corrente", ARGOMENTO_0)
    tutti = vista.get("argomenti") or []
    ultimi: dict[str, str] = {}
    for t in vista["turni"]:
        frasi = [x for x, *_ in detto(t)]
        if frasi:
            ultimi[t.get("argomento", ARGOMENTO_0)] = frasi[-1]
    cur = next((a for a in tutti if a["id"] == corrente), None) or {"id": corrente}
    parte = [dict(a, ultimo=ultimi.get(a["id"], "")) for a in reversed(tutti)
             if a["id"] != corrente and (a.get("titolo") or ultimi.get(a["id"]))]
    return {"corrente": {k: cur.get(k) for k in ("id", "titolo", "ora")}, "da_parte": parte}


def _voce_indice(a: dict) -> str:
    titolo = f"«{_corto(a.get('titolo') or 'la conversazione di prima', 60)}»"
    extra = []
    if a.get("ora"):
        extra.append(f"dalle {a['ora']}")
    lasciato = [str(x.get("cosa") if isinstance(x, dict) else x) for x in a.get("lasciato") or ()]
    if lasciato:
        extra.append("rimasto aperto: " + "; ".join(_corto(x, 80) for x in lasciato))
    if a.get("ultimo"):
        extra.append(f"ultima cosa detta: «{_corto(a['ultimo'], 100)}»")
    return titolo + (f" ({', '.join(extra)})" if extra else "")


def indice(vista: dict, massimo: int = 5) -> str | None:
    """L'indice degli argomenti messi da parte (un messaggio di sistema dopo il riassunto,
    fermo finché non cambia argomento: resta nella cache del prefisso), o None."""
    parte = argomenti(vista)["da_parte"][:massimo]
    if not parte:
        return None
    return INDICE_MSG.format(voci="; ".join(_voce_indice(a) for a in parte))


def fughe(eventi, msgs: list[dict]) -> int:
    """Quanti eventi non visibili al modello hanno il loro testo nei messaggi proiettati
    (`fughe_proiezione`, § 6): deve restare 0 per costruzione."""
    contenuti = "\n".join(str(m.get("content") or "") for m in msgs)
    n = 0
    for e in eventi:
        if e.vis in ("modello", "turno"):
            continue
        for k in ("testo", "parole", "contenuto"):
            v = e.dati.get(k)
            if isinstance(v, str) and len(v.strip()) >= 8 and v.strip() in contenuti:
                n += 1
                break
    return n


def proposta_aperta(eventi) -> dict | None:
    """Il fold della macchina (§ 3.3, solo lettura qui): l'ultima proposta_aperta senza la sua
    chiusura, o None."""
    aperta = None
    for e in eventi:
        if e.tipo == "proposta_aperta":
            aperta = e
        elif e.tipo == "proposta_chiusa" and aperta is not None \
                and e.dati.get("id") == aperta.dati.get("id"):
            aperta = None
    return dict(aperta.dati) if aperta is not None else None


def tipi_coperti() -> set:
    return set(PROIEZIONE_CONTESTO) & set(PROIEZIONE_TURNI) & set(TIPI)


__all__ = ["PROIEZIONE_CONTESTO", "PROIEZIONE_TURNI", "ESCLUSO", "Escluso", "ATTI_FUORI",
           "Forma", "FORMA", "turni", "messaggi", "contesto", "detto", "testo_assistente",
           "fughe", "proposta_aperta", "modulo_testo", "Evento", "promemoria_interrotta",
           "promemoria_cosa_fare", "argomenti", "indice"]
