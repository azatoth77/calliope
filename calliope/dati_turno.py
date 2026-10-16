"""
I dati del turno che cambiano di rado, nella storia in sola aggiunta (16/10/2026, issue #95).

**Il difetto.** I dati del turno (ora e chi parla, ricordi, avvisi ai tutori, nota e riassunto
della stanza, ricerca anticipata…) stanno subito prima della domanda e non entrano nella storia:
alla richiesta dopo spariscono, e la richiesta nuova differisce da quella di prima a partire da
loro. Gemma 4 ha strati con attenzione a finestra scorrevole (SWA): Ollama (motore di llama.cpp)
ne tiene in memoria solo gli ultimi `n_swa + n_ubatch` token e per tornare più indietro usa i
*context checkpoint* creati alla fine di ogni lettura del prompt. Se il punto di differenza sta più
di ~`n_ubatch` (512) token prima della fine della richiesta di prima, nessun checkpoint serve, quelli
dopo il punto si cancellano e il motore riparte dal primo rimasto: si rilegge tutta la storia, a
ogni turno («ripresi» fermi a ~18 000 sulla DGX il 15/10, 85 turni su 118). Misure e meccanismo in
docs/aree/contesto-conversazione.md, sezione «La cache del prefisso e la finestra scorrevole».

**La correzione.** Ciò che cambia di rado (i ricordi di chi parla, gli avvisi ai tutori, il
riassunto della stanza) entra nella storia **solo quando cambia**, come le righe della stanza
(`Brain._con_stanza`): un `Fisso` legato alla frase della persona del turno in cui è cambiato
(segno `_dati` sul messaggio, solo in memoria), nei turni dopo nello stesso posto e uguale byte per
byte. Nei dati del turno resta ciò che cambia a ogni turno, sotto un tetto in token
(`dati_turno_tetto_token`, in Brain).

- Una versione nuova si **aggiunge** dopo le vecchie (la cache resta); le vecchie restano dove sono.
- Se la versione nuova **toglie** una voce di quella visibile (un ricordo dimenticato), le versioni
  vecchie di quel blocco escono dalla storia e la nuova, intera, entra al turno in corso: la cache
  si rompe una volta, dal posto della versione più vecchia (regola `dati_stabili_rifatti`). Così un
  ricordo dimenticato non resta davanti al modello.
- Un pezzo il cui turno non c'è più nella storia (taglio, compressione) se ne va con lui; alla
  richiesta dopo il blocco, se c'è ancora, torna al turno in corso.
- Solo nelle conversazioni di una persona: in quella anonima condivisa in compagnia i ricordi sono
  di chi parla adesso, quindi restano nei dati del turno (come prima).

Solo libreria standard, nessun testo su disco: i pezzi stanno in `Conversazione.dati_fissi`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Le voci di un blocco fatto di elementi tra virgolette basse (i ricordi): per sapere se una
# versione nuova ne toglie qualcuna
_VOCI = re.compile(r"«([^»]+)»")


@dataclass
class Fisso:
    """Un dato che cambia di rado, messo nella storia al turno `n` (numero del pezzo nella
    conversazione) davanti alla frase della persona."""
    n: int
    nome: str                     # «ricordi», «avvisi», «stanza_riassunto»
    testo: str
    voci: frozenset | None = None  # None: un testo intero, che si sostituisce solo aggiungendo
    esterno: str = ""             # le parole d'altri dentro il testo (per la politica dei tool)

    @property
    def caratteri(self) -> int:
        return len(self.testo)

    def messaggio(self) -> dict:
        return {"role": "system", "content": self.testo}


def voci_di(testo: str) -> frozenset:
    """Le voci tra «» di un testo (i ricordi): frozenset vuoto se non ce n'è."""
    return frozenset(x.strip() for x in _VOCI.findall(testo or "") if x.strip())


def segni(x) -> list[int]:
    """I numeri dei pezzi da un segno `_dati` (un numero o un elenco)."""
    if isinstance(x, int) and not isinstance(x, bool):
        return [x]
    if isinstance(x, (list, tuple)):
        return [v for v in x if isinstance(v, int) and not isinstance(v, bool)]
    return []


def stato(conv) -> list:
    """I pezzi della conversazione (`Conversazione.dati_fissi`), creati se mancano."""
    if not isinstance(getattr(conv, "dati_fissi", None), list):
        conv.dati_fissi, conv.dati_n = [], 0
    return conv.dati_fissi


def prepara(conv, blocchi: list[tuple], ancore: set[int]) -> dict:
    """Decide i pezzi di questo turno.

    `blocchi`: (nome, testo, a_voci[, esterno]) dei dati che cambiano di rado per chi parla adesso
    (testo "" = il blocco oggi non c'è); `a_voci`: il blocco è fatto di voci tra «» (i ricordi) e
    una voce tolta lo rifà; `esterno`: le parole d'altri del testo (il riassunto della stanza). `ancore`: i numeri dei pezzi legati alle frasi ancora nella storia prima del
    turno in corso.

    Restituisce {"nuovi": [Fisso] da mettere davanti alla frase di questo turno, "storia":
    {n: Fisso} dei pezzi dei turni prima, "rifatti": [nomi], "orfani": quanti pezzi se ne sono
    andati col loro turno}. Cambia `conv.dati_fissi` e `conv.dati_n`."""
    pezzi = stato(conv)
    orfani = [p for p in pezzi if p.n not in ancore]
    if orfani:
        pezzi[:] = [p for p in pezzi if p.n in ancore]
    nuovi, rifatti = [], []
    for nome, testo, a_voci, *resto in blocchi:
        testo = testo or ""
        esterno = str(resto[0] or "") if resto else ""
        vecchi = [p for p in pezzi if p.nome == nome]
        ultimo = vecchi[-1] if vecchi else None
        if ultimo is not None and ultimo.testo == testo:
            continue                                  # già davanti al modello, uguale
        voci = voci_di(testo) if a_voci else None
        if a_voci and vecchi:
            visibili = frozenset().union(*(p.voci or frozenset() for p in vecchi))
            if not visibili <= (voci or frozenset()):
                # Una voce tolta (un ricordo dimenticato): via le versioni vecchie, la cache si
                # rompe una volta; la nuova, se c'è, entra intera qui
                pezzi[:] = [p for p in pezzi if p.nome != nome]
                rifatti.append(nome)
                ultimo = None
        if not testo:
            continue        # il blocco non c'è più (avvisi scaduti): il vecchio resta, era vero
        conv.dati_n = int(getattr(conv, "dati_n", 0) or 0) + 1
        nuovi.append(Fisso(conv.dati_n, nome, testo, voci, esterno))
    pezzi.extend(nuovi)
    nuovi_n = {p.n for p in nuovi}
    return {"nuovi": nuovi, "storia": {p.n: p for p in pezzi if p.n not in nuovi_n},
            "rifatti": rifatti, "orfani": len(orfani)}


def con_fissi(msgs: list[dict], ancore: dict) -> list[dict]:
    """`msgs` (la storia prima del turno in corso, con le righe della stanza già al loro posto)
    con i pezzi dei dati fissi, ognuno subito prima della frase del suo turno: lo stesso posto e lo
    stesso testo di quando sono entrati (dopo le righe della stanza di quel turno, come allora)."""
    if not ancore:
        return list(msgs)
    out = []
    for m in msgs:
        if isinstance(m, dict) and m.get("role") == "user":
            for n in segni(m.get("_dati")):
                if n in ancore:
                    out.append(ancore[n].messaggio())
        out.append(m)
    return out


def caratteri(conv) -> int:
    """I caratteri dei pezzi della conversazione (per il taglio della storia in token)."""
    return sum(p.caratteri for p in getattr(conv, "dati_fissi", None) or ())
