"""
I comandi a voce di un gioco (11/10/2026, richiesta approvata da Dario): il gioco aperto sullo
schermo di un satellite dichiara nel manifesto un elenco breve e chiuso di comandi
(`scheda.ascolta`, calliope/estensioni/scheda.py), ognuno con una o più forme («uno», «la porta
uno», «1»); una frase che corrisponde **per intero** a una forma di un comando attivo diventa una
mossa e va dritta al gioco, senza il modello (regola `gioco_comando`, calliope/ciclo.py).

È il caso ammesso dal principio 10 (docs/ricerche/2026-10-01-regole-deterministiche.md): una forma
chiusa e breve, riconosciuta per intero, con un effetto reversibile (una mossa in un gioco).
Ammesse solo le normalizzazioni della forma: maiuscole, accenti e punteggiatura, i numeri in
parole o in cifre («tre» = «3»), il nome davanti («Calliope, tre»), anche storpiato come lo
riconosce la wake word testuale (wakeword._plain_words). Mai una parola dentro una frase: «apri
la porta tre per favore» e «tre gatti» vanno al modello, che ha `gioco_comando` per passare al
gioco un comando dell'elenco detto in altro modo.

Qui solo il testo: forme, normalizzazione e confronto. Il resto (quale gioco è aperto e dove,
la finestra senza nome, chi gioca) sta in calliope/schermi/giochi.py e calliope/ciclo.py.
"""
from __future__ import annotations

import re

from .wakeword import _NAME_MARK, _plain_words, closing_kind, exit_request

# ── i numeri in parole (0–100), in forma senza accenti come li dà _plain_words ──
_UNITA = ["zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove"]
_DIECI = ["dieci", "undici", "dodici", "tredici", "quattordici", "quindici", "sedici",
          "diciassette", "diciotto", "diciannove"]
_DECINE = {2: "venti", 3: "trenta", 4: "quaranta", 5: "cinquanta", 6: "sessanta",
           7: "settanta", 8: "ottanta", 9: "novanta"}


def _numeri() -> dict[str, str]:
    out = {w: str(i) for i, w in enumerate(_UNITA)}
    out.update({w: str(10 + i) for i, w in enumerate(_DIECI)})
    for d, w in _DECINE.items():
        out[w] = str(d * 10)
        for u in range(1, 10):
            unita = _UNITA[u]
            # «ventuno», «ventotto»: la vocale della decina cade davanti a uno e otto
            base = w[:-1] if u in (1, 8) else w
            out[base + unita] = str(d * 10 + u)
    out["cento"] = "100"
    # «un», «una»: come «uno» («la porta una» e «la porta 1» sono la stessa forma)
    out["un"] = out["una"] = "1"
    return out


NUMERI = _numeri()

# ── i limiti dell'elenco (validati nel manifesto) ──
MAX_COMANDI = 24
MAX_FORME = 6
MAX_FORMA_CARATTERI = 40
MAX_FORMA_PAROLE = 5
ID_COMANDO = re.compile(r"^[a-z0-9][a-z0-9_]{0,23}$")


def normalizza(testo: str, nomi=("Calliope",)) -> str:
    """La frase nella forma di confronto: minuscole senza accenti né punteggiatura, numeri in
    cifre, senza il nome davanti. «Calliope, la porta TRE!» → «la porta 3»."""
    parole = _plain_words(testo or "", nomi)
    while parole and parole[0] == _NAME_MARK:
        parole = parole[1:]
    out = []
    for p in parole:
        p = p.replace("_", "")
        if not p:
            continue
        if p.isdigit():
            p = str(int(p)) if len(p) <= 6 else p
        out.append(NUMERI.get(p, p))
    return " ".join(out)


class ElencoNonValido(ValueError):
    pass


def riservata(forma: str, nomi=("Calliope",)) -> str | None:
    """Una forma che coprirebbe una regola fissa della voce: l'uscita («esci», «spegniti») e lo
    stop («basta», «stop»). Il motivo, o None. «Ricomincia» invece si può: dentro un gioco che lo
    dichiara riavvia il gioco, non la conversazione (lo decide l'ordine delle fasi del ciclo)."""
    if exit_request(forma, nomi):
        return "è un'uscita della voce"
    if closing_kind(forma, nomi) == "silenzio":
        return "ferma la voce («basta», «stop»)"
    return None


def valida_elenco(comandi, nomi=("Calliope",), massimo: int = MAX_COMANDI) -> dict[str, list[str]]:
    """L'elenco dei comandi di `scheda.ascolta.comandi`, validato: {id: [forme]} (le forme come
    scritte, già controllate). Accetta {id: [forme]} o [{"id", "forme"}]. Solleva
    ElencoNonValido con un messaggio per chi scrive il manifesto. `massimo`: quanti comandi
    (13/10: l'elenco piatto della macchina a stati, con gli slot espansi, arriva a 64)."""
    if isinstance(comandi, list):
        coppie = []
        for c in comandi:
            if not isinstance(c, dict):
                raise ElencoNonValido("«ascolta.comandi»: un oggetto {\"id\": [forme]}")
            coppie.append((c.get("id"), c.get("forme")))
    elif isinstance(comandi, dict):
        coppie = list(comandi.items())
    else:
        raise ElencoNonValido("«ascolta.comandi»: un oggetto {\"uno\": [\"uno\", \"la porta "
                              "uno\"], …}")
    if not coppie or len(coppie) > massimo:
        raise ElencoNonValido(f"«ascolta.comandi»: da 1 a {massimo} comandi")
    out: dict[str, list[str]] = {}
    viste: dict[str, str] = {}
    for cid, forme in coppie:
        if not isinstance(cid, str) or not ID_COMANDO.match(cid):
            raise ElencoNonValido(f"«ascolta.comandi»: nome del comando non valido «{cid}» "
                                  "(minuscole, cifre e _, al più 24)")
        if cid in out:
            raise ElencoNonValido(f"«ascolta.comandi»: «{cid}» due volte")
        if isinstance(forme, str):
            forme = [forme]
        if not isinstance(forme, list) or not forme or len(forme) > MAX_FORME:
            raise ElencoNonValido(f"«ascolta.comandi.{cid}»: da 1 a {MAX_FORME} forme")
        pulite = []
        for f in forme:
            if not isinstance(f, (str, int)) or isinstance(f, bool):
                raise ElencoNonValido(f"«ascolta.comandi.{cid}»: ogni forma è un testo breve")
            f = str(f).strip()
            n = normalizza(f, nomi)
            if (not n or len(f) > MAX_FORMA_CARATTERI
                    or len(n.split()) > MAX_FORMA_PAROLE):
                raise ElencoNonValido(
                    f"«ascolta.comandi.{cid}»: «{f[:50]}» non va (da 1 a {MAX_FORMA_PAROLE} "
                    f"parole, al più {MAX_FORMA_CARATTERI} caratteri, senza il solo nome)")
            perche = riservata(f, nomi)
            if perche:
                raise ElencoNonValido(f"«ascolta.comandi.{cid}»: «{f}» {perche}: scegli "
                                      "un'altra parola")
            if n in viste and viste[n] != cid:
                raise ElencoNonValido(f"«ascolta.comandi»: «{f}» vale sia per «{viste[n]}» sia "
                                      f"per «{cid}»")
            viste[n] = cid
            if f not in pulite:
                pulite.append(f)
        out[cid] = pulite
    return out


def forme_normalizzate(comandi: dict[str, list[str]], nomi=("Calliope",)) -> dict[str, str]:
    """{forma normalizzata: id} per il confronto."""
    out = {}
    for cid, forme in (comandi or {}).items():
        for f in forme:
            n = normalizza(f, nomi)
            if n:
                out.setdefault(n, cid)
    return out


def trova(testo: str, comandi: dict[str, list[str]], attivi=None,
          nomi=("Calliope",)) -> str | None:
    """Il comando (id) a cui la frase corrisponde **per intero**, tra quelli `attivi` (None:
    tutti i dichiarati). Mai una parola dentro la frase."""
    if not testo or not comandi:
        return None
    n = normalizza(testo, nomi)
    if not n:
        return None
    cid = forme_normalizzate(comandi, nomi).get(n)
    if cid is None:
        return None
    if attivi is not None and cid not in attivi:
        return None
    return cid


def ha_il_nome(testo: str, nomi=("Calliope",)) -> bool:
    """La frase comincia con il nome (anche storpiato, come per la wake word testuale)."""
    parole = _plain_words(testo or "", nomi)
    return bool(parole) and parole[0] == _NAME_MARK


__all__ = ["NUMERI", "normalizza", "valida_elenco", "forme_normalizzate", "trova", "riservata",
           "ElencoNonValido", "ha_il_nome"]
