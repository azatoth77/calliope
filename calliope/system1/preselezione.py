"""
Il secondo decisore System 1: **quali tool servono a questa frase?** (15/10/2026, richiesta di
Dario del 14/10; progetto e misure in docs/ricerche/2026-10-15-preselezione-tool.md).

Il modello della voce vede ogni volta tutti gli schemi dei tool (75–85, ~6–15 mila token): con
un elenco fisso stanno nella cache del prefisso di Ollama, ma il renderer di gemma4 li mette **in
testa** al prompt, quindi un elenco che cambia fa rileggere tutto (prompt di sistema, storia,
dati del turno). Per questo non si sceglie un sottoinsieme qualsiasi a ogni turno: il decisore
sceglie fra **due insiemi stabili**,

- «nucleo»: i tool di tutti i giorni (ora e date, calcoli, agenda, liste, memoria, casa, meteo,
  ricerche e notizie, la conversazione), `NUCLEO`, o quelli passati a `Preselettore(nucleo=…)`;
- «tutti»: l'elenco di oggi.

Decide «nucleo» solo quando nessun tool fuori dal nucleo è vicino alla frase; nel dubbio
«tutti» (il richiamo deve restare ~100 %: togliere il tool giusto vuol dire un «non posso» o
un tool sbagliato). In più segna i `TOP` tool più vicini, per misurare anche la
variante «per famiglie» (che romperebbe la cache a ogni cambio).

Come decide: un indice di **prototipi** costruito dagli schemi stessi (nome del tool, prima
frase della descrizione e le frasi d'esempio tra «…» che le descrizioni hanno già), e una
somiglianza fra la frase (e quella di prima, per i seguiti come «E in camera?») e i prototipi.
Due codificatori (principio 2, stessa interfaccia `vettori(testi) -> list`):

- «parole» (di serie): n-grammi di caratteri e parole con pesi tf-idf, sola libreria standard,
  < 5 ms, nessun modello, nessuna memoria;
- «embedding»: il modello di embedding di Ollama (quello delle conversazioni nello script
  della DGX), sulla CPU (`conversazioni.Embedder`): più bravo con le parafrasi, ma
  tiene un modello residente in più su Ollama.

Più i segnali di struttura, che non leggono il testo: un tool fuori dal nucleo usato nella
conversazione, una proposta aperta o un tool nominato nei dati del turno, una foto o un file con
la frase → «tutti».

Principio 10: non è una regola sul testo.

*[Storico, 15/10: l'ombra nel ciclo (`preselezione_tool: ombra`) scriveva nel registro dei
turni l'insieme scelto accanto ai tool usati, e `calliope stato --turni` ne faceva il
richiamo.]* Il 15/10 la misura sulla DGX è stata negativa (§ 7 della ricerca: richiamo 84 %
sui turni veri, «nucleo» nel 9 %, ogni cambio d'insieme +0,4–0,5 s contro ~40 ms guadagnati).
Dal 16/10 (issue #25, scelta B) l'ombra è tolta dal ciclo con i suoi campi di configurazione e
la sezione di `calliope stato`: resta solo il decisore, come strumento di misura per
`prove/manuali/preselezione_dgx.py --registro` (il richiamo sui turni veri, senza modello) e
`prove/prova_preselezione.py` (il banco a secco). Nessun modulo di Calliope lo importa.
"""
from __future__ import annotations

import math
import re
import time
import unicodedata
import zlib
from dataclasses import dataclass, field

from . import Decisione

NUCLEO_SCELTA, TUTTI = "nucleo", "tutti"
CODIFICATORI = ("parole", "embedding")
TOP = 8                         # i tool più vicini della variante «per famiglie»

# Il nucleo di serie: i tool di tutti i giorni (15/10, dai giri veri: tempo, agenda, liste,
# memoria, casa, ricerche, conversazione). Un tool che non c'è nell'installazione si ignora
NUCLEO = (
    "ora_attuale", "data_oggi", "calcola", "data_calcola",
    "timer_imposta", "promemoria_imposta", "agenda_elenca", "agenda_annulla",
    "appuntamento_aggiungi", "appuntamenti_elenca",
    "lista_aggiungi", "lista_leggi", "lista_togli",
    "ricorda", "dimentica", "chi_parla",
    "casa_comando", "casa_stato", "meteo_leggi",
    "biblioteca_cerca", "web_cerca", "notizie",
    "schermo_mostra", "calliope_stato",
    "conversazione_nuova", "argomento", "conversazione_cerca", "proposta_rispondi",
)

# Le famiglie, solo per le misure (variante «per famiglie» e righe di `calliope stato`); un tool
# che non è qui (un'estensione) è della famiglia «altri»
FAMIGLIE = {
    "tempo": ("ora_attuale", "data_oggi", "calcola", "data_calcola"),
    "agenda": ("timer_imposta", "promemoria_imposta", "agenda_elenca", "agenda_annulla",
               "appuntamento_aggiungi", "appuntamenti_elenca"),
    "liste": ("lista_aggiungi", "lista_leggi", "lista_togli"),
    "memoria": ("ricorda", "dimentica"),
    "persone": ("chi_parla", "elenca_voci", "cambia_voce", "elenca_utenti",
                "rinomina_interlocutore", "registra_utente"),
    "casa": ("casa_comando", "casa_stato", "casa_integrazione", "meteo_leggi",
             "citta_casa_salva"),
    "sapere": ("biblioteca_cerca", "web_cerca", "notizie"),
    "pc": ("pc_stato", "pc_volume", "pc_media", "pc_luminosita", "pc_apri_app", "pc_blocca",
           "pc_cerca_file", "pc_apri_file", "pc_guarda"),
    "documenti": ("documento_crea", "documento_modifica", "documento_leggi", "modello_compila",
                  "anagrafica_cerca", "anagrafica_salva"),
    "archivio": ("archivio_cerca", "archivio_scadenze", "archivio_somma", "immagine_archivia",
                 "allegato_archivia"),
    "file": ("immagine_guarda", "allegato_leggi", "cassetto_gestisci"),
    "agenti": ("lavoro_affida", "lavoro_stato", "lavoro_annulla", "programma_esegui",
               "lavoro_rispondi", "lavoro_risultato"),
    "sviluppo": ("sviluppo_apri", "sviluppo_passo", "sviluppo_collauda", "sviluppo_chiedi",
                 "sviluppo_correggi", "estensione_gestisci"),
    "schermi": ("schermo_mostra", "schermo_gestisci", "schede_pulisci"),
    "dialogo": ("conversazione_nuova", "conversazione_cerca", "conversazioni_dimentica",
                "argomento", "proposta_rispondi"),
    "minori": ("richiesta_tutore", "minore_gestisci"),
    "studio": ("studio", "studio_pagina_leggi"),
    "calliope": ("calliope_stato", "installa_proponi", "installa_avvia", "installa_gestisci",
                 "dati_conservati"),
    "stanza": ("stanza_pausa", "stanza_cerca", "conoscenti", "conoscente_livello"),
}
_FAMIGLIA = {t: f for f, tt in FAMIGLIE.items() for t in tt}


def famiglia(nome: str) -> str:
    return _FAMIGLIA.get(str(nome), "altri")


# ─────────────────────────────── prototipi dagli schemi ───────────────────────────────
_ESEMPIO = re.compile(r"«([^»]{3,120})»")
_FRASE = re.compile(r"^(.+?[.:;])(\s|$)", re.S)


def prototipi(schemas) -> list[tuple[str, str]]:
    """(tool, testo) per ogni schema: il nome in parole con la prima frase della descrizione,
    e ogni frase d'esempio tra «…» della descrizione (le descrizioni ne hanno già: «cosa c'è
    nella lista della spesa?»)."""
    out = []
    for s in schemas or ():
        fn = s.get("function", s) if isinstance(s, dict) else {}
        nome = str(fn.get("name") or "")
        if not nome:
            continue
        desc = str(fn.get("description") or "")
        m = _FRASE.match(desc.strip())
        prima = m.group(1) if m else desc[:160]
        out.append((nome, f"{nome.replace('_', ' ')}. {prima}"))
        for es in _ESEMPIO.findall(desc):
            es = es.strip(" .…")
            if len(es) >= 3:
                out.append((nome, es))
    return out


# ─────────────────────────────── codificatori ───────────────────────────────
def _norma(testo: str) -> str:
    t = unicodedata.normalize("NFKD", str(testo or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


class CodificaParole:
    """n-grammi di caratteri (3–5, dentro le parole) e parole intere, pesati tf-idf sui
    prototipi; vettori sparsi normalizzati (dict). Solo libreria standard."""
    nome = "parole"

    def __init__(self):
        self.idf: dict[int, float] = {}

    @staticmethod
    def _tratti(testo: str) -> dict[int, float]:
        conta: dict[int, float] = {}
        for w in _norma(testo).split():
            k = zlib.crc32(("w:" + w).encode())
            conta[k] = conta.get(k, 0.0) + 1.0
            g = f" {w} "
            for n in (3, 4, 5):
                for i in range(max(0, len(g) - n + 1)):
                    k = zlib.crc32(g[i:i + n].encode())
                    conta[k] = conta.get(k, 0.0) + 1.0
        return conta

    def adatta(self, testi: list[str]):
        df: dict[int, int] = {}
        for t in testi:
            for k in self._tratti(t):
                df[k] = df.get(k, 0) + 1
        n = max(1, len(testi))
        self.idf = {k: math.log((1 + n) / (1 + d)) + 1.0 for k, d in df.items()}

    def vettori(self, testi: list[str], domanda: bool = False) -> list[dict[int, float]]:
        out = []
        idf_nuovo = math.log(1 + max(1, len(self.idf))) + 1.0
        for t in testi:
            v = {k: (1.0 + math.log(c)) * self.idf.get(k, idf_nuovo)
                 for k, c in self._tratti(t).items()}
            norma = math.sqrt(sum(x * x for x in v.values())) or 1.0
            out.append({k: x / norma for k, x in v.items()})
        return out

    @staticmethod
    def simile(a: dict, b: dict) -> float:
        if len(a) > len(b):
            a, b = b, a
        return sum(x * b.get(k, 0.0) for k, x in a.items())


class CodificaEmbedding:
    """Il modello di embedding di Ollama (o di un server OpenAI), sulla CPU: i vettori dei
    prototipi si calcolano una volta (e di nuovo se cambiano gli schemi)."""
    nome = "embedding"

    def __init__(self, embedder):
        self.embedder = embedder

    def adatta(self, testi):
        pass

    def vettori(self, testi, domanda: bool = False):
        import numpy as np
        testi, out = list(testi), []
        for i in range(0, len(testi), 32):        # a lotti: i prototipi sono qualche centinaio
            out.extend(self.embedder.vettori(testi[i:i + 32], domanda=domanda))
        return [np.asarray(v, dtype="float32") for v in out]

    @staticmethod
    def simile(a, b) -> float:
        return float((a * b).sum())


# ─────────────────────────────── il decisore ───────────────────────────────
@dataclass(frozen=True)
class Richiesta:
    """Ciò che serve al decisore: la frase, quella di prima della stessa conversazione, i tool
    usati nella conversazione, i nomi di tool che compaiono nei dati del turno o nella
    proposta aperta, e se con la frase sono arrivati foto o file."""
    testo: str
    prima: str | None = None
    recenti: tuple[str, ...] = ()
    nominati: tuple[str, ...] = ()
    foto: bool = False


@dataclass(frozen=True)
class Scelta(Decisione):
    perche: str = ""
    schemi: int = 0
    schemi_tutti: int = 0
    nucleo_max: float = 0.0
    fuori_max: float = 0.0
    fuori_tool: str = ""
    top: tuple = ()
    nomi: frozenset = field(default_factory=frozenset)


class Preselettore:
    """`decide(Richiesta) -> Scelta` fra «nucleo» e «tutti» (System 1, stessa interfaccia della
    fine del turno). `aggiorna(schemas)` ricostruisce l'indice se l'elenco è cambiato."""
    nome = "preselezione"
    scelte = (NUCLEO_SCELTA, TUTTI)

    def __init__(self, codifica=None, nucleo=None, margine: float = 0.0,
                 soglia_fuori: float = 1.0):
        self.codifica = codifica or CodificaParole()
        self.nucleo_voluto = tuple(nucleo or NUCLEO)
        # «tutti» se un tool fuori dal nucleo arriva a `margine` dal migliore del nucleo, o
        # supera `soglia_fuori` in assoluto (tarati sul banco: docs/ricerche/…)
        self.margine = float(margine)
        self.soglia_fuori = float(soglia_fuori)
        self._nomi: tuple[str, ...] = ()
        self._proto: list[tuple[str, object]] = []
        self.nucleo: frozenset = frozenset()

    def aggiorna(self, schemas) -> bool:
        nomi = tuple(sorted(str((s.get("function") or {}).get("name") or "")
                            for s in schemas or () if isinstance(s, dict)))
        if nomi == self._nomi and self._proto:
            return False
        pp = prototipi(schemas)
        testi = [t for _, t in pp]
        self.codifica.adatta(testi)
        vv = self.codifica.vettori(testi)
        self._proto = [(n, v) for (n, _), v in zip(pp, vv)]
        self._nomi = nomi
        self.nucleo = frozenset(n for n in self.nucleo_voluto if n in set(nomi))
        return True

    def punteggi(self, testo: str, prima: str | None = None) -> dict[str, float]:
        """Per ogni tool la somiglianza più alta fra i suoi prototipi e la frase (e la frase
        con quella di prima, per i seguiti)."""
        domande = [testo] + ([f"{prima} {testo}"] if prima else [])
        qq = self.codifica.vettori(domande, domanda=True)
        sim = self.codifica.simile
        out: dict[str, float] = {}
        for nome, v in self._proto:
            s = max(sim(q, v) for q in qq)
            if s > out.get(nome, -1.0):
                out[nome] = s
        return out

    def decide(self, r: Richiesta) -> Scelta:
        t0 = time.perf_counter()
        tutti = set(self._nomi)
        n_tutti = len(tutti)
        nucleo = self.nucleo
        p = self.punteggi(r.testo, r.prima) if self._proto else {}
        top = tuple(n for n, _ in sorted(p.items(), key=lambda kv: -kv[1])[:TOP])
        nmax = max((v for n, v in p.items() if n in nucleo), default=0.0)
        fuori = [(v, n) for n, v in p.items() if n not in nucleo]
        fmax, ftool = max(fuori, default=(0.0, ""))
        perche = ""
        if not nucleo or not self._proto:
            perche = "senza_indice"
        elif r.foto:
            perche = "foto_o_file"
        elif any(x in tutti and x not in nucleo for x in r.recenti):
            perche = "tool_recente"
        elif any(x in tutti and x not in nucleo for x in r.nominati):
            perche = "tool_nei_dati"
        elif fmax >= self.soglia_fuori:
            perche = "fuori_vicino"
        elif fmax >= nmax - self.margine:
            perche = "fuori_vicino"
        scelta = TUTTI if perche else NUCLEO_SCELTA
        sicurezza = 0.5 + min(0.5, max(0.0, nmax - self.margine - fmax)) if not perche else 1.0
        nomi = frozenset(tutti) if scelta == TUTTI else nucleo
        return Scelta(scelta, round(sicurezza, 3), round((time.perf_counter() - t0) * 1000, 2),
                      perche=perche or "nucleo", schemi=len(nomi), schemi_tutti=n_tutti,
                      nucleo_max=round(nmax, 3), fuori_max=round(fmax, 3), fuori_tool=ftool,
                      top=top, nomi=nomi)


def preso(scelta: Scelta | dict, accettati) -> bool:
    """La frase è presa: l'insieme scelto contiene almeno uno dei tool accettati (nessun tool
    accettato: sempre)."""
    acc = [a for a in accettati or () if a]
    if not acc:
        return True
    nomi = scelta.nomi if isinstance(scelta, Scelta) else set(scelta.get("nomi") or ())
    return any(a in nomi for a in acc)


# ─────────────────────── i segnali dalla conversazione ───────────────────────
def tool_recenti(history, max_messaggi: int = 40) -> tuple[str, ...]:
    """I nomi dei tool chiamati negli ultimi messaggi della conversazione (formato interno di
    Brain: {"role": "assistant", "tool_calls": [{"name": …}]})."""
    nomi = []
    for m in list(history or ())[-max_messaggi:]:
        if isinstance(m, dict) and m.get("role") == "assistant":
            for c in m.get("tool_calls") or ():
                n = c.get("name") if isinstance(c, dict) else None
                if n is None and isinstance(c, dict):
                    n = (c.get("function") or {}).get("name")
                if n and n not in nomi:
                    nomi.append(str(n))
    return tuple(nomi)


def _ultima_domanda(history) -> str | None:
    for m in reversed(list(history or ())):
        if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str):
            c = m["content"].strip()
            # I messaggi dei dati del turno («[Dati del turno…]») non sono frasi della persona
            if c and not c.startswith("["):
                return c[-300:]
    return None


def nominati(testi, nomi) -> tuple[str, ...]:
    """I nomi di tool (interi) che compaiono nei testi dati (dati del turno, proposta aperta)."""
    t = " ".join(str(x) for x in testi if x)
    if not t:
        return ()
    return tuple(n for n in nomi if n and re.search(rf"\b{re.escape(n)}\b", t))


# Tarati sul banco a secco del 15/10 (prove/banco_preselezione.py, 148 frasi, codifica
# «parole»): con margine 0,05 un tool mancato, da 0,10 nessuno (46 frasi su 148 a «nucleo»).
# La soglia assoluta resta spenta (1,0): il margine basta
MARGINE = 0.10
SOGLIA_FUORI = 1.0
