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


def controlla(attese: dict, turno: dict | None, testo: str, extra: dict | None = None
              ) -> list[str]:
    """Gli scostamenti dalle attese (vuoto = passo riuscito). `testo`: le frasi sentite dal
    satellite (o la risposta del registro); `extra`: suoni, servizi dell'HA e azioni del PC
    fatti durante il passo, annuncio sentito."""
    extra = extra or {}
    errori = []
    turno = turno or {}
    tool = _tool(turno)
    regole = list(turno.get("regole") or [])
    risposta = testo or turno.get("risposta") or ""
    if attese.get("muto"):
        if risposta.strip():
            errori.append(f"doveva tacere, ha detto: {risposta[:80]!r}")
        return errori
    if "tool" in attese and not any(t in tool for t in attese["tool"]):
        errori.append(f"tool attesi {attese['tool']}, chiamati {tool}")
    for t in attese.get("tool_tutti") or []:
        if t not in tool:
            errori.append(f"manca il tool {t} (chiamati {tool})")
    nt = attese.get("no_tool")
    if nt is True and tool:
        errori.append(f"nessun tool atteso, chiamati {tool}")
    elif isinstance(nt, (list, tuple)):
        vietati = [t for t in tool if t in nt]
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
    if "annuncio" in attese and not extra.get("annuncio"):
        errori.append(f"annuncio {attese['annuncio'][0]!r} non sentito entro "
                      f"{attese['annuncio'][1]} s")
    return errori


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
