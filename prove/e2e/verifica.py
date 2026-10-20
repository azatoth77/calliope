"""
Il controllo di un passo (06/10/2026): la riga del registro dei turni dell'istanza (tool,
regole, esito, livello, chi parla) e ciò che il satellite ha sentito (le frasi), contro le
attese del copione. Funzioni pure: le prova `prove/prova_e2e_copioni.py` a secco.
"""
from __future__ import annotations

import difflib
import re
import unicodedata


def _tool(turno: dict) -> list[str]:
    return [t.get("nome") for t in (turno or {}).get("tool") or [] if isinstance(t, dict)]


def _regola_ok(voluta: str, regole: list[str]) -> bool:
    if voluta.endswith("*"):
        return any(r.startswith(voluta[:-1]) for r in regole)
    return voluta in regole


def _lista(v) -> list:
    return list(v) if isinstance(v, (list, tuple)) else [v]


def _porta_ok(voluta: str, decisioni: list[str]) -> bool:
    """«regola» (con «*» finale un prefisso) o «regola:esito» tra le decisioni della porta
    stretta del passo, scritte come «regola:esito»."""
    regola, _, esito = voluta.partition(":")
    for d in decisioni:
        r, _, e = d.partition(":")
        if (r.startswith(regola[:-1]) if regola.endswith("*") else r == regola) and (
                not esito or e == esito):
            return True
    return False


def controlla(attese: dict, turno: dict | None, testo: str, extra: dict | None = None
              ) -> list[str]:
    """Gli scostamenti dalle attese (vuoto = passo riuscito). `testo`: le frasi sentite dal
    satellite (o la risposta del registro); `extra`: suoni, servizi dell'HA e azioni del PC
    fatti durante il passo, annuncio sentito; dal 20/10 anche `porta` (le decisioni della porta
    stretta scritte durante il passo, «regola:esito»), `sviluppo` ({fase, stato} dello sviluppo
    toccato per ultimo, dopo il passo), `log` (il log dell'istanza durante il passo, annuncio
    compreso) e `schede` (le schede arrivate allo schermo dello studio)."""
    extra = extra or {}
    if attese.get("o"):
        # Strade alternative (20/10, revisione della PR #196): l'impossibile fermato
        # all'analisi o dal piano dell'agente. Basta una; se nessuna va, gli scostamenti della
        # prima
        resto = {k: v for k, v in attese.items() if k != "o"}
        prove_o = [controlla({**resto, **alt}, turno, testo, extra) for alt in attese["o"]]
        if any(not e for e in prove_o):
            return []
        return prove_o[0] + [f"(e nessuna delle {len(prove_o)} strade alternative)"]
    # «est_@»: il tool dell'estensione del copione (`extra["estensione"]`, il nome interno
    # dallo sviluppo che l'ha creata: revisione della PR #196, «est_*» accettava ogni estensione)
    nome = extra.get("estensione")
    if any("est_@" in (attese.get(k) or ()) for k in ("tool", "tool_tutti", "no_tool")
           if isinstance(attese.get(k), (list, tuple))):
        attese = {k: ([f"est_{nome}" if x == "est_@" else x for x in v]
                      if k in ("tool", "tool_tutti", "no_tool") and isinstance(v, (list, tuple))
                      else v) for k, v in attese.items()}
    errori = []
    turno = turno or {}
    tool = _tool(turno)
    regole = list(turno.get("regole") or [])
    risposta = testo or turno.get("risposta") or ""
    if attese.get("muto"):
        if risposta.strip():
            errori.append(f"doveva tacere, ha detto: {risposta[:80]!r}")
        return errori
    # «est_*»: un prefisso (il tool di un'estensione ha il nome che le dà l'agente, 20/10)
    if "tool" in attese and not any(_regola_ok(t, tool) for t in attese["tool"]):
        errori.append(f"tool attesi {attese['tool']}, chiamati {tool}")
    for t in attese.get("tool_tutti") or []:
        if not _regola_ok(t, tool):
            errori.append(f"manca il tool {t} (chiamati {tool})")
    nt = attese.get("no_tool")
    if nt is True and tool:
        errori.append(f"nessun tool atteso, chiamati {tool}")
    elif isinstance(nt, (list, tuple)):
        vietati = [t for t in tool if any(_regola_ok(x, [t]) for x in nt)]
        if vietati:
            errori.append(f"tool da non chiamare: {vietati}")
    for r in attese.get("regole") or []:
        if not _regola_ok(r, regole):
            errori.append(f"manca la regola {r} (scattate {regole})")
    for r in attese.get("no_regole") or []:
        if _regola_ok(r, regole):
            errori.append(f"regola da non far scattare: {r}")
    if "esito" in attese:
        voluti = attese["esito"] if isinstance(attese["esito"], (list, tuple)) else [attese["esito"]]
        if turno.get("esito") not in voluti:
            errori.append(f"esito {turno.get('esito')!r}, atteso {voluti}")
    if "livello" in attese and turno.get("livello") != attese["livello"]:
        errori.append(f"livello {turno.get('livello')!r}, atteso {attese['livello']!r}")
    if "chi" in attese:
        nome = (turno.get("voce") or {}).get("nome")
        if attese["chi"] is None:
            if nome:
                errori.append(f"riconosciuto come {nome}, doveva essere un ospite")
        elif nome != attese["chi"]:
            errori.append(f"riconosciuto come {nome!r}, atteso {attese['chi']!r}")
    if attese.get("testo") and not any(re.search(p, risposta, re.I) for p in attese["testo"]):
        errori.append(f"risposta senza {attese['testo']}: {risposta[:160]!r}")
    for p in attese.get("non_testo") or []:
        if re.search(p, risposta, re.I):
            errori.append(f"risposta con {p!r}: {risposta[:160]!r}")
    if attese.get("suoni") and not extra.get("suoni"):
        errori.append("nessun suono d'ascolto sul satellite")
    servizi = extra.get("ha") or []
    for s in attese.get("ha") or []:
        if s not in servizi:
            errori.append(f"HA finto: manca {s} (eseguiti {servizi})")
    if attese.get("ha_no") and servizi:
        errori.append(f"HA finto: eseguiti {servizi}, non doveva")
    azioni = extra.get("pc") or []
    for a in attese.get("pc") or []:
        if a not in azioni:
            errori.append(f"PC finto: manca {a} (fatte {azioni})")
    stati = extra.get("voce_studio") or []
    if attese.get("voce_studio") and not any(x in ("pensa", "parla") for x in stati):
        errori.append(f"lo schermo dello studio non ha mostrato «pensa» o «parla» ({stati})")
    if attese.get("voce_studio_ferma") and any(x in ("pensa", "parla") for x in stati):
        errori.append(f"lo schermo dello studio mostra la voce di un'altra stanza ({stati})")
    # Estensioni, sviluppo e giochi (20/10, issue #75)
    porta = list(extra.get("porta") or [])
    for v in attese.get("porta") or []:
        if not _porta_ok(v, porta):
            errori.append(f"porta stretta: manca {v} (decisioni {porta})")
    for v in attese.get("porta_no") or []:
        if _porta_ok(v, porta):
            errori.append(f"porta stretta: {v} non doveva esserci")
    sv = extra.get("sviluppo") or {}
    if "sviluppo" in attese and sv.get("fase") not in _lista(attese["sviluppo"]):
        errori.append(f"sviluppo in fase {sv.get('fase')!r}, attesa {_lista(attese['sviluppo'])}")
    if "sviluppo_stato" in attese and sv.get("stato") not in _lista(attese["sviluppo_stato"]):
        errori.append(f"sviluppo {sv.get('stato')!r}, atteso {_lista(attese['sviluppo_stato'])}")
    log = extra.get("log") or ""
    for p in attese.get("log") or []:
        if not re.search(p, log, re.I):
            errori.append(f"nel log dell'istanza manca {p!r}")
    for p in attese.get("no_log") or []:
        m = re.search(p, log, re.I)
        if m:
            errori.append(f"nel log dell'istanza c'è {m.group(0)[:120]!r}")
    if attese.get("scheda"):
        schede = extra.get("schede") or []
        if not any(re.search(p, s, re.I) for p in attese["scheda"] for s in schede):
            errori.append(f"nessuna scheda sullo studio con {attese['scheda']} "
                          f"({len(schede)} schede)")
    if attese.get("gioco"):
        g = turno.get("gioco") if isinstance(turno.get("gioco"), dict) else {}
        for k, rx in attese["gioco"].items():
            if g.get(k) is None or not re.search(str(rx), str(g.get(k)), re.I):
                errori.append(f"gioco.{k} = {g.get(k)!r}, atteso {rx!r}")
    if attese.get("annuncio_testo"):
        # L'annuncio intero: la frase che ha combaciato e quelle dette dopo fino al silenzio
        intero = f"{extra.get('annuncio') or ''} {extra.get('seguito') or ''}"
        for p in attese["annuncio_testo"]:
            if not re.search(p, intero, re.I):
                errori.append(f"nell'annuncio manca {p!r}: {intero[:160]!r}")
    if "annuncio" in attese and not extra.get("annuncio"):
        errori.append(f"annuncio {attese['annuncio'][0]!r} non sentito entro "
                      f"{attese['annuncio'][1]} s")
    return errori


def domande(*testi: str) -> str:
    """Le sole frasi che finiscono con «?» (seconda revisione della PR #196): `se_domanda`
    scatta su una domanda, non su un titolo o una mancanza detti nell'annuncio.
    Con ogni domanda anche la frase subito prima (la domanda dell'agente in due frasi: «…non
    conosco il calendario della raccolta. Me lo dici?»); conta anche «?» seguito da una
    virgoletta di chiusura («?»», «?"»)."""
    frasi = re.split(r"(?<=[.!?])\s+|(?<=[.!?][»”\"')])\s+",
                     " ".join(str(t or "") for t in testi))
    tenute = []
    for i, f in enumerate(frasi):
        if re.search(r"\?[»”\"')]*$", f.strip()):
            if i and frasi[i - 1] not in tenute:
                tenute.append(frasi[i - 1])
            tenute.append(f)
    return " ".join(tenute)


def normalizza(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", s))


def somiglianza(a: str, b: str) -> float:
    """Somiglianza tra due testi (0–1) a parole normalizzate."""
    x, y = normalizza(a).split(), normalizza(b).split()
    if not x and not y:
        return 1.0
    return difflib.SequenceMatcher(None, x, y).ratio()


def parole_sfida(risposta: str) -> str | None:
    """Le parole della frase di sfida («Per conferma ripeti: girasole, matita, …»)."""
    m = re.search(r"ripeti\s*[:,]?\s*(.+?)(?:\.\s|\.$|$)", risposta, re.I)
    return m.group(1).strip() if m else None


def quantili(v: list[float]) -> dict:
    v = sorted(x for x in v if isinstance(x, (int, float)))
    if not v:
        return {"n": 0}
    q = lambda p: v[min(len(v) - 1, int(p * len(v)))]  # noqa: E731
    return {"n": len(v), "mediana": round(q(0.5), 2), "p75": round(q(0.75), 2),
            "p90": round(q(0.9), 2), "max": round(v[-1], 2)}
