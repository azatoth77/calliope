"""
La corsia veloce delle risposte a una proposta (10/10/2026, passo 1 del progetto «lo stato del
dialogo come macchina a stati», docs/ricerche/2026-10-10-macchina-stati.md § 3.4).

Il significato di una risposta lo decide il modello (`proposta_rispondi`, principio 10). Qui
c'è solo il caso stretto che il principio ammette: una **forma chiusa e breve detta per intero**
(«sì», «no grazie», «annulla», «basta», «esci», «ricominciamo», «grazie»), con un effetto
reversibile (al più una conferma in più). Serve a non aspettare il modello e a reggere quando
il modello sbaglia o non risponde. Tutto il resto, anche «sì» con altre parole («Sì, però fallo
dopo», «Sì, puoi andare»), va al modello: `forma_chiusa` restituisce None.

Ogni pezzo della frase (tra virgole e punti), tolti il nome e i riempitivi in testa e in coda,
dev'essere una forma dell'elenco; pezzi di tipo diverso valgono solo in coppie chiare (un «sì» o
un «no» con un «grazie»: «Sì, grazie», «No, grazie»). Un'uscita o «ricominciamo» valgono solo
per la frase intera e senza un «sì» («Sì, puoi andare» resta al modello).

Dal passo 1 è **in ombra** (`dialogo_interprete: ombra`): l'esito si scrive nel registro dei
turni (campo `dialogo_ombra`, `forma_chiusa`) e non decide niente. I casi e i contrari sono in
prove/prova_testo.py.
"""
from __future__ import annotations

import re

from .storpiature import suggerisci
from .wakeword import _NAME_MARK, _plain_words, nuova_conversazione, uscita_intera

SI, NO, STOP, GRAZIE, USCITA, NUOVA = "si", "no", "stop", "grazie", "uscita", "nuova"

# Le forme, senza accenti (come _plain_words: «sì» → «si», «perché» → «perche»)
FORME = {
    SI: frozenset({
        "si", "si si", "certo", "certamente", "certo che si", "ma certo", "si certo", "vai",
        "vai pure", "procedi", "procedi pure", "ok", "okay", "ok vai", "va bene", "d accordo",
        "fallo", "fallo pure", "falla", "falli", "esatto", "volentieri", "perche no", "si dai",
        "dai si", "assolutamente", "si per favore", "si grazie", "si va bene", "ok va bene",
        "confermo", "si confermo", "esatto si"}),
    NO: frozenset({
        "no", "no no", "no grazie", "annulla", "lascia stare", "lascia perdere", "non importa",
        "meglio di no", "per ora no", "assolutamente no", "no lascia stare", "no lascia perdere",
        "non serve", "non fa niente", "no annulla", "niente", "no niente"}),
    STOP: frozenset({"basta", "stop", "fermati", "ferma", "zitta", "silenzio", "basta cosi",
                     "smettila", "basta grazie"}),
    GRAZIE: frozenset({"grazie", "grazie mille", "perfetto", "ottimo", "benissimo",
                       "ti ringrazio", "gentilissima", "perfetto grazie", "ottimo grazie",
                       "grazie tante"}),
}
# Riempitivi in testa e in coda a un pezzo (mai in mezzo)
RIEMPITIVI = frozenset({"allora", "beh", "be", "eh", "ehm", "mah", "ma", "ecco", "dunque",
                        "pure", "ah", "oh", "mh", "mmh", "uhm"})
# Un «sì» nella frase toglie l'uscita dalla corsia veloce («Sì, puoi andare»: al modello)
_PAROLE_SI = frozenset({"si", "ok", "okay", "certo"})


def _pezzo(parole: list[str]) -> str:
    p = [w for w in parole if w != _NAME_MARK]
    while p and p[0] in RIEMPITIVI:
        p.pop(0)
    while p and p[-1] in RIEMPITIVI:
        p.pop()
    return " ".join(p)


def tipo_pezzo(pezzo: str, name="Calliope") -> str | None:
    """Il tipo della forma chiusa di un pezzo di frase, o None."""
    p = _pezzo(_plain_words(pezzo, name))
    if not p:
        return ""
    for tipo, forme in FORME.items():
        if p in forme:
            return tipo
    return None


def forma_chiusa(testo: str, name="Calliope") -> str | None:
    """La forma chiusa della frase intera: "si", "no", "stop", "grazie", "uscita", "nuova", o
    None (la frase va al modello)."""
    t = (testo or "").strip()
    if not t:
        return None
    parole = [w for w in _plain_words(t, name) if w != _NAME_MARK]
    if not parole:
        return None                      # il nome da solo non è una risposta
    if nuova_conversazione(t, name):
        return NUOVA
    tipi = []
    for pezzo in re.split(r"[,.;:!?…\-–]+", t):
        if not pezzo.strip():
            continue
        tp = tipo_pezzo(pezzo, name)
        if tp is None:
            tipi = None
            break
        if tp:
            tipi.append(tp)
    if tipi:
        s = set(tipi)
        if len(s) == 1:
            return tipi[0]
        if s == {SI, GRAZIE}:
            return SI
        if s == {NO, GRAZIE}:
            return NO
        if s == {STOP, GRAZIE}:
            return STOP
        if s == {NO, STOP}:
            return NO
        return None
    # Un'uscita: la frase intera, e senza un «sì» in mezzo
    if uscita_intera(t, name) and not (set(parole) & _PAROLE_SI):
        return USCITA
    # «Annulla» storpiato da Whisper, da solo («Annullahi.», «Anzi, no, a nulla.», 10/10,
    # calliope/storpiature.py): a una proposta vale «no», un effetto reversibile. Le altre
    # storpiature («Spendilo», «Chiudin») restano al modello, con un dato del turno
    sugg = suggerisci(t, name)
    if sugg and sugg["corsia"]:
        return NO
    return None


# ─────────────── una risposta senza parole riconoscibili (10/10) ───────────────
# Terzo giro vero della DGX, 10:39:07: a «…Lo chiudo?» Whisper ha scritto «CQD» (era forse «Sì,
# chiudi») e il modello l'ha preso per un «sì»: lo sviluppo si è chiuso. Una frase senza nessuna
# parola italiana riconoscibile (una sigla, sillabe, rumore) non è una risposta: riguarda la
# trascrizione, che il modello non vede come tale (principio 10), e l'effetto è una domanda in
# più («Non ho capito: lo chiudo?», politica.consenso_irriconoscibile). Niente dizionario: le
# parole brevi chiuse qui sotto, e per le altre la forma delle parole italiane (una vocale, e in
# fondo una vocale); una sigla tutta maiuscola non è una parola. Le storpiature note
# (calliope/storpiature.py: «Spendilo», «Chiudin», «Annullahi») restano al loro percorso.
PAROLE_BREVI = frozenset(
    "si no ok okay yes sì è e o ed od ma se ne ci vi mi ti lo la le li gli il i un uno una a ad "
    "da di in con per su tra fra fa fai va vai do sto sta hai ha ho più piu già gia qui qua là la' "
    "lì li' poi ora tu io lui lei noi voi chi che ciò cio mio tuo suo due tre sei non bel bar gas "
    "sud nord est ovest".split())
_VOCALI = frozenset("aeiouàèéìíòóùú")
_TOKEN = re.compile(r"[^\W\d_]+|\d+")


def parola_riconoscibile(parola: str) -> bool:
    """Una parola che può essere italiana: una delle brevi, un numero, o almeno tre lettere con
    una vocale e una vocale in fondo, e non una sigla tutta maiuscola."""
    w = str(parola or "")
    lw = w.lower()
    if not lw:
        return False
    if lw.isdigit() or lw in PAROLE_BREVI:
        return True
    if len(lw) < 3 or (w.isupper() and len(w) <= 5):
        return False
    return any(c in _VOCALI for c in lw) and lw[-1] in _VOCALI


def senza_parole(testo: str, name="Calliope") -> bool:
    """La frase non ha nessuna parola riconoscibile, tolto il nome («CQD», «Mh.», «Ehm…»).
    False per una storpiatura nota di una forma chiusa (ha il suo percorso)."""
    t = str(testo or "").strip()
    if not t:
        return False
    if suggerisci(t, name):
        return False
    parole = [w for w in _TOKEN.findall(t)
              if [x for x in _plain_words(w, name) if x != _NAME_MARK]]
    return not any(parola_riconoscibile(w) for w in parole)

