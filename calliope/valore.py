"""
Sicurezza per valore (08/10/2026, docs/ricerche/2026-10-07-sicurezza-per-valore.md § 5, fasi 2
e 3; decisioni di Dario D1–D8 dell'08/10).

La politica dei tool (calliope/politica.py) decide **per conversazione**: con un dato non
fidato di mezzo ogni azione «pericolosa» chiede conferma, anche quando la persona l'ha chiesta
con le sue parole e gli argomenti sono suoi. Il 07/10 sono state 15,8 domande ogni 100 turni,
28 su 41 falsi positivi. Qui la stessa chiamata si giudica con tre domande, tutte
deterministiche:

1. **chi l'ha chiesta** (l'ancora: le parole del tool nella frase di questo turno, il «sì» alla
   domanda o un'intenzione confermata);
2. **da dove vengono gli argomenti** (provenienza per valore, `etichetta`): `detto` in questa
   frase, `persona` prima, `fidato` da un tool interno, `scelta` in un insieme chiuso, `modello`
   senza fonte, `dato` da un dato non fidato;
3. **che effetto ha** (`effetto`, classi E0–E4): lettura, locale reversibile, persistente o
   condiviso, esce o esegue codice, fiducia e sicurezza fisica.

**Fase 2, attiva: memoria dell'intento** (`Intenzione`). Un'azione confermata dalla persona
riconosciuta (il «sì» con la voce, la sfida superata, la richiesta ripetuta) che poi fallisce
resta un'intenzione aperta per quel tool, quel bersaglio e quella persona: la chiamata corretta
(«riprova», l'indice giusto, «ti ho detto di sì») si esegue senza un'altra domanda (regola
`intento_confermato`). Si chiude con il successo, con un «no» o «lascia stare», con un'azione
riuscita di un altro tool, con un dato nuovo, alla chiusura della conversazione o dopo
`intento_valido_s` (D4: 10 minuti). Mai per un bersaglio diverso, un'altra persona, una frase
scritta, né per i tool con la frase di sfida (registrare voci, schermi, minori, installazioni):
lì la domanda è sull'identità e si rifà.

**Fase 3, in ombra: la matrice** (`decidi_valore`, § 5.4 del documento). Per ogni chiamata con
un dato non fidato di mezzo la politica calcola anche la decisione nuova e la scrive nel registro
dei turni (`politica_ombra` della chiamata: decisione vera, decisione nuova, regola, effetto,
etichette degli argomenti; nessun valore). Vale quella di oggi finché `politica_per_valore` è
spento (D5: due giorni d'ombra, poi una riga per accenderla e una per tornare indietro).

Sono vincoli di sicurezza e di permesso su un'azione già scelta dal modello (principio 10): non
decidono che cosa vuole la persona, solo se chiedere. Ogni decisione ha un nome nel registro.
Solo libreria standard, sotto il millisecondo per chiamata.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, replace

from . import politica as pol
from . import provenienza as prov

# ─────────────────────────── tipi degli argomenti (§ 5.2) ───────────────────────────
# bersaglio: su che cosa si agisce (deve venire dalla persona o da un tool fidato)
# azione: un valore chiuso che sceglie l'azione (enum: «approva», «scollega», «alza»)
# scelta: un valore chiuso o limitato (numeri entro i limiti del tool, durate, booleani)
# indice: un numero in un elenco; vale l'etichetta dell'elenco («indice:pc_cerca_file»)
# contenuto: che cosa si scrive (voci di una lista, testo di un ricordo o di un promemoria)
# testo_libero: lo scrive il modello espandendo la richiesta (compito di un lavoro)
# ignora: non cambia l'azione (id della proposta)
BERSAGLIO, AZIONE, SCELTA, CONTENUTO, LIBERO, IGNORA = (
    "bersaglio", "azione", "scelta", "contenuto", "testo_libero", "ignora")
INDICE = "indice"

B, Z, S, C, L, X = BERSAGLIO, AZIONE, SCELTA, CONTENUTO, LIBERO, IGNORA

# Gli argomenti di ogni tool d'azione (Classe.argomenti del documento). Un tool d'azione senza
# riga, o un argomento che non c'è, vale «bersaglio» (chiuso per difetto): prove/prova_valore.py
# fallisce se un tool d'azione di un registro completo non è qui
ARGOMENTI: dict[str, dict[str, str]] = {
    "cambia_voce": {"voce": S, "tono": Z, "per_tutti": S, "modalita": Z},
    "rinomina_interlocutore": {"nome": B},
    "registra_utente": {"nome": B, "nascita": C, "maggiorenne": S, "tutori": B},
    "timer_imposta": {"durata": S, "nome": C, "cambia": Z},
    "promemoria_imposta": {"testo": C, "quando": S, "cambia": Z},
    "agenda_annulla": {"cosa": B},
    "appuntamento_aggiungi": {"cosa": C, "quando": S, "cambia": Z},
    "lista_aggiungi": {"cose": C, "lista": B},
    "lista_togli": {"cose": B, "lista": B},
    "ricorda": {"fatto": C, "per_tutti": Z, "nascita": C},
    "dimentica": {"fatto": B},
    "pc_volume": {"azione": Z, "valore": S},
    "pc_media": {"comando": Z},
    "pc_luminosita": {"azione": Z, "valore": S},
    "pc_apri_app": {"app": B},
    "pc_blocca": {},
    # il file è nell'ultimo elenco di chi parla: lo fanno pc_cerca_file e offri_file (i
    # documenti appena scritti), tool interni
    "pc_apri_file": {"risultato": "indice:pc_cerca_file", "pc": B},
    "documento_crea": {"formato": S, "richiesta": L, "titolo": C},
    "documento_modifica": {"modifica": L},
    "casa_comando": {"comando": B},
    "schermo_gestisci": {"azione": Z, "codice": B, "stanza": B, "personale": S, "persona": B},
    "delega_lavoro": {"tipo": Z, "compito": L, "vincoli": L, "proposta": X, "file": B,
                      "allegato": "indice:allegato", "formato": S, "modello": S},
    "lavori_annulla": {"quale": Z},
    "lavori_esegui": {"lavoro": B, "dati": C},
    "lavori_rispondi": {"lavoro": B, "risposta": C},
    "modello_compila": {"modello": Z, "dati": C, "proposta": X},
    "anagrafica_salva": {"azione": Z, "nome": B, "dati": C, "proposta": X},
    "conversazioni_dimentica": {},
    "pc_guarda": {"cosa": Z},
    "immagine_archivia": {"foto": "indice:foto"},
    "allegato_archivia": {"allegato": "indice:allegato"},
    "richiesta_tutore": {"cosa": Z, "nome": B, "minuti": S},
    "minore_gestisci": {"nome": B, "azione": Z, "valore": C},
    "installa_avvia": {"azione": B},
    "installa_gestisci": {"azione": Z},
    "estensione_crea": {"compito": L, "nome": C, "gia_fatto_da": S, "come_chiederlo": L,
                        "proposta": X, "gioco": S},
    "estensioni_gestisci": {"azione": Z, "nome": B, "esecuzione": B, "sempre": S},
}

# Gli elenchi a cui punta un indice: fidato se lo fa un tool interno (o è un file della
# persona), dato se lo fa un tool con una fonte non fidata (provenienza.FONTI)
ELENCHI_FIDATI = frozenset({"pc_cerca_file", "allegato", "foto"})


def argomenti_di(name: str, spec=None) -> dict | None:
    """I tipi degli argomenti del tool: `ToolSpec.argomenti` (estensioni), poi la tabella;
    None se il tool non li dichiara."""
    a = getattr(spec, "argomenti", None)
    if isinstance(a, dict):
        return a
    return ARGOMENTI.get(name)


# ─────────────────────────── classi d'effetto (§ 5.3) ───────────────────────────
E0, E1, E2, E3, E4 = 0, 1, 2, 3, 4
NOMI_EFFETTO = {E0: "E0", E1: "E1", E2: "E2", E3: "E3", E4: "E4"}

# Casa per effetto (D2): luci E1; clima e tapparelle E2 (aprono la casa); nomi delicati E4
# (cancello, serrature, gas… calliope/casa/regole.py: si leggono e non si comandano); il resto
# non si sa, quindi E3
_LUCI = re.compile(r"(?<![a-zà-ù])(luc[ei]|lampad|faretti|faretto|abat|lampion|led)", re.I)
_CLIMA = re.compile(r"(?<![a-zà-ù])(clima|condizionat|riscald|termostat|temperatur|caldaia|"
                    r"tapparell|serrand|persian|tend[ae]|scur[io]|ventil)", re.I)
_DELICATI = re.compile(r"(?<![a-zà-ù])(cancell[oi]|serratur|portone|porta|garage|gas|allarm|"
                       r"antifurt|valvol|basculant)", re.I)


def _casa(a: dict) -> int:
    c = pol._s(a, "comando")
    if _DELICATI.search(c):
        return E4
    if _CLIMA.search(c):
        return E2
    if _LUCI.search(c):
        return E1
    return E3


def _delega(a: dict) -> int:
    # D1: una ricerca è E2 (resta in casa, l'agente ha il Ripulitore e la rete pubblica in
    # uscita); codice, documenti e il resto E3
    return E2 if pol._s(a, "tipo").lower() == "ricerca" else E3


def _ricorda(a: dict) -> int:
    # D3: per tutti E2; personale E2 anche lui, ma senza parole dal dato si esegue come oggi
    # (fatto_detto o ancorata): la differenza la fanno le etichette
    return E2


EFFETTI: dict[str, object] = {
    # E1: locale, di chi parla o del dispositivo davanti a lei, si disfa con una frase
    "pc_volume": E1, "pc_luminosita": E1, "pc_media": E1, "pc_apri_file": E1,
    "timer_imposta": E1, "promemoria_imposta": E1, "cambia_voce": E1, "documento_crea": E1,
    "documento_modifica": E1, "pc_blocca": E1, "immagine_archivia": E1,
    "allegato_archivia": E1,
    # E2: resta, altri lo vedono o cambia le risposte future
    "lista_aggiungi": E2, "lista_togli": E2, "ricorda": _ricorda, "dimentica": E2,
    "appuntamento_aggiungi": E2, "agenda_annulla": E2, "anagrafica_salva": E2,
    "modello_compila": E2, "richiesta_tutore": E2, "lavori_rispondi": E2,
    "lavori_annulla": E2, "estensione_crea": E2, "pc_guarda": E2,
    # E3: esce di casa, esegue codice o non si disfa
    "lavori_esegui": E3, "installa_avvia": E3, "installa_gestisci": E3, "pc_apri_app": E3,
    "estensioni_gestisci": E3, "conversazioni_dimentica": E3,
    # E4: fiducia e sicurezza fisica
    "registra_utente": E4, "rinomina_interlocutore": E4, "schermo_gestisci": E4,
    "minore_gestisci": E4,
    # dipendono da un argomento
    "casa_comando": _casa, "delega_lavoro": _delega,
}


def effetto(name: str, args: dict, spec=None) -> int:
    """La classe d'effetto della chiamata. Le letture (classe «sicuro») sono E0; senza effetto
    dichiarato vale E3 (chiuso per difetto, come «senza classe vale pericoloso»)."""
    cl = pol.classe_di(name, spec)
    if cl.classe == pol.SICURO:
        return E0
    if cl.sola_lettura is not None and pol._s(args, cl.sola_lettura[0]).lower() in cl.sola_lettura[1]:
        return E0
    e = getattr(spec, "effetto", None)
    if e is None:
        e = EFFETTI.get(name, E3)
    try:
        return int(e(args or {})) if callable(e) else int(e)
    except Exception:  # noqa: BLE001 — nel dubbio, E3
        return E3


# ─────────────────────────── memoria dell'intento (fase 2) ───────────────────────────

@dataclass
class Intenzione:
    """Un'azione confermata dalla persona riconosciuta che non è ancora riuscita."""
    tool: str
    bersaglio: dict                  # gli argomenti che dicono su che cosa (normalizzati)
    persona: object                  # la chiave di chi l'ha confermata (Brain._speaker_key)
    aperta: float = field(default_factory=time.monotonic)
    argomenti: dict = field(default_factory=dict)   # tutti quelli confermati
    volte: int = 0                   # quante volte è valsa dopo la conferma


# «No», «lascia stare», «annulla», «non importa», «basta così»: l'intenzione si chiude. Forma
# chiusa breve **per intero**, o «no» in testa (principio 10: effetto reversibile, la persona
# può richiederla)
ANNULLA = re.compile(
    r"^\W*(?:calliope\W+)?(?:no(?:\W|$)|annulla|lascia (?:stare|perdere)|non (?:importa|serve|"
    r"farlo|lo fare|più)|basta(?: così)?\W*$|niente\W*$|lascia\W*$|stop\W*$|ferma(?:ti)?\W*$)",
    re.I)


def chiude(testo: str) -> bool:
    """La frase chiude le intenzioni aperte della conversazione."""
    return bool(ANNULLA.search(testo or ""))


def chiave_intento(name: str, args: dict, cosa: str | None = None, spec=None) -> dict:
    """Il bersaglio di una chiamata: gli argomenti `bersaglio`, `azione`, `indice` e
    `testo_libero` (il compito di un lavoro: un compito diverso è un'altra azione). Il
    contenuto no (il valore del volume, l'indice corretto che punta allo stesso file). Con la
    descrizione del bersaglio vero (Classe.descrivi: «apra «Spese (2)»») vale quella al posto
    dell'indice. Senza tipi dichiarati: tutti gli argomenti che contano."""
    tipi = argomenti_di(name, spec)
    a = args or {}
    if tipi is None:
        return {k: v for k, v in pol._conta(pol.classe_di(name, spec), a).items()}
    out = {}
    for k, v in a.items():
        tipo = tipi.get(k, BERSAGLIO)
        if tipo.startswith(INDICE) and cosa:
            out["_bersaglio"] = cosa
            continue
        if tipo in (BERSAGLIO, AZIONE, LIBERO) or tipo.startswith(INDICE):
            out[k] = v
    return out


def _stesso(a: dict, b: dict) -> bool:
    return pol._uguali(a, b, None)


def intento_aperto(name: str, args: dict, t, ctx, cosa: str | None = None, spec=None):
    """L'intenzione aperta che vale per questa chiamata, o None.

    Vale se: stesso tool, stesso bersaglio, stessa persona, entro `intento_valido_s`; la frase
    è della persona (voce, breve o zona grigia della sua conversazione, non scritta né da un
    ospite); nessun dato nuovo con questa frase; nessuna parola dal dato in un argomento
    importante che la persona non abbia già confermato."""
    if t is None or not getattr(t, "intenzioni", None) or t.dato_nuovo:
        return None
    cl = pol.classe_di(name, spec)
    if cl.sfida:
        return None
    sc = getattr(ctx, "speaker_ctx", None)
    if (sc is None or getattr(sc, "current_speaker", None) is None
            or getattr(sc, "identified_by", None) not in ("voce", "breve", "conversazione")):
        return None
    valido = float(getattr(getattr(ctx, "cfg", None), "intento_valido_s", 600) or 0)
    ora = time.monotonic()
    chiave = chiave_intento(name, args, cosa, spec)
    for i in reversed(t.intenzioni):
        if (i.tool != name or i.persona != t.persona or (valido and ora - i.aperta > valido)
                or not _stesso(chiave, i.bersaglio)):
            continue
        k, fuori, _ = pol.valori_esterni(cl, args or {}, t)
        if fuori and not pol._uguali({k: (args or {}).get(k)}, {k: i.argomenti.get(k)}, [k]):
            return None
        return i
    return None


def nuova_intenzione(name: str, args: dict, t, cosa: str | None = None, spec=None):
    return Intenzione(name, chiave_intento(name, args, cosa, spec), t.persona,
                      argomenti=dict(args or {}))


def aggiorna(intenzioni: list, esito: dict | None, ok: bool, in_sospeso: bool = False,
             valido_s: float = 600.0):
    """Dopo l'esecuzione di un tool (Brain): un'intenzione confermata o usata che riesce si
    chiude; una che fallisce resta aperta (gli errori sono errori, la conferma non si
    riapre); un'azione riuscita di un altro tool chiude le intenzioni degli altri tool."""
    if intenzioni is None:
        return
    ora = time.monotonic()
    intenzioni[:] = [i for i in intenzioni if not valido_s or ora - i.aperta <= valido_s]
    if not isinstance(esito, dict) or esito.get("decisione") != "esegui":
        return
    nome = esito.get("tool")
    i = esito.get("intento")
    if ok:
        if esito.get("azione"):
            chiave = esito.get("chiave") or {}
            intenzioni[:] = [x for x in intenzioni if x.tool == nome
                             and not _stesso(x.bersaglio, chiave)]
        return
    if i is None or in_sospeso:
        return
    intenzioni[:] = [x for x in intenzioni if not (x.tool == i.tool and x.persona == i.persona
                                                   and _stesso(x.bersaglio, i.bersaglio))]
    i.volte += 1 if esito.get("usata") else 0
    intenzioni.append(i)
    del intenzioni[:-5]


# ─────────────────────────── provenienza per valore (fase 3) ───────────────────────────
DETTO, PERSONA, FIDATO, SCELTO, MODELLO, DATO = (
    "detto", "persona", "fidato", "scelta", "modello", "dato")
ORDINE = {DETTO: 0, PERSONA: 1, FIDATO: 2, SCELTO: 3, MODELLO: 4, DATO: 5}


def _gettoni_numeri(testo) -> set[str]:
    """Le cifre di un testo, anche dette in lettere («tre» → «3»)."""
    out = set()
    for g in pol._gettoni(testo):
        if g.isdigit():
            out.add(str(int(g)) if len(g) < 6 else g)
    inverso = {v: str(k) for k, v in pol._NUMERI.items()}
    out |= {inverso[g] for g in pol._gettoni(testo) if g in inverso}
    return out


@dataclass
class Fonti:
    """Le parole di ogni fonte, calcolate una volta per chiamata."""
    frase: set
    persona: set
    fidato: set
    dato: set
    numeri_frase: set
    numeri_persona: set
    numeri_dato: set
    foto: bool

    @classmethod
    def da(cls, t, fidati=()) -> "Fonti":
        esterni = " ".join(x for _, x in (t.esterni or ()))
        fid = " ".join(str(x) for x in (fidati or ()))
        return cls(prov.parole(t.testo), prov.parole(t.persona_txt), prov.parole(fid),
                   prov.parole(esterni), _gettoni_numeri(t.testo), _gettoni_numeri(t.persona_txt),
                   _gettoni_numeri(esterni), "foto" in (t.contaminazione or ()))


def _testo(valore) -> str | None:
    if isinstance(valore, (list, tuple)):
        if not all(isinstance(x, (str, int, float)) for x in valore):
            return None
        return " ".join(str(x) for x in valore)
    if isinstance(valore, bool) or valore is None:
        return ""
    if isinstance(valore, (str, int, float)):
        return str(valore)
    return None                       # annidato: non si sa


def etichetta(valore, tipo: str, f: Fonti) -> str:
    """L'etichetta di provenienza di un valore: la peggiore fra le sue parole (§ 5.2)."""
    if tipo in (AZIONE, SCELTA, IGNORA):
        return SCELTO
    if tipo.startswith(INDICE):
        elenco = tipo.partition(":")[2]
        return FIDATO if elenco in ELENCHI_FIDATI else DATO
    testo = _testo(valore)
    if testo is None:
        return DATO
    peggiore = None
    for w in prov.parole(testo):
        if w in f.frase:
            e = DETTO
        elif w in f.persona:
            # Detto solo prima e anche nel dato: per un bersaglio può averlo scelto il dato
            # (il «latte» del 06/10)
            e = DATO if tipo == BERSAGLIO and w in f.dato else PERSONA
        elif w in f.dato:
            # Il dato prima del fidato: un valore del dato che un tool interno ha ripetuto
            # (il nome di un timer messo da una pagina) non diventa fidato
            e = DATO
        elif w in f.fidato:
            e = FIDATO
        else:
            e = DATO if (tipo == BERSAGLIO and f.foto) else MODELLO
        if peggiore is None or ORDINE[e] > ORDINE[peggiore]:
            peggiore = e
    for n in _gettoni_numeri(testo):
        e = (DETTO if n in f.numeri_frase else PERSONA if n in f.numeri_persona
             else DATO if n in f.numeri_dato else MODELLO)
        if peggiore is None or ORDINE[e] > ORDINE[peggiore]:
            peggiore = e
    return peggiore or SCELTO


# Nomi propri, sigle, numeri, indirizzi: le parole «distintive» di un testo libero. Le parole
# comuni che il modello aggiunge espandendo la richiesta («approfondita», «analizzando») non
# contano (§ 5.2: la quota di parole della persona in un compito ha mediana 0,17)
_DISTINTIVA = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+|https?://\S+|www\.\S+|"
                         r"(?<=[^.!?:\s«\"'(]\s)[A-ZÀ-Ý][\wà-ÿ']{2,}|\b[A-Z]{2,}\b|\b\w*\d\w*\b")


def distintive(valore, f: Fonti) -> list[str]:
    """Le parole distintive del valore che stanno in un dato non fidato e non nelle parole
    della persona (ora o prima)."""
    testo = _testo(valore) or ""
    out = []
    for m in _DISTINTIVA.finditer(" " + testo):
        for w in prov.parole(m.group(0)) | _gettoni_numeri(m.group(0)):
            if w in f.persona or w in f.frase or w in f.numeri_frase or w in f.numeri_persona:
                continue
            if w in f.dato or w in f.numeri_dato:
                out.append(w)
    return sorted(set(out))


def personali(valore, t, ctx) -> list[str]:
    """I tipi di dato personale nel valore che la persona non ha detto in questa frase (D7:
    il compito di delega_lavoro, ciò che esce di casa): nomi delle persone di casa, stringhe
    private, codici fiscali, IBAN, email, telefoni. Solo i tipi, mai i dati."""
    testo = _testo(valore) or ""
    if not testo:
        return []
    try:
        from .web.privacy import Ripulitore, nomi_da, privati_da_config
        cfg = getattr(ctx, "cfg", None)
        rip = Ripulitore(nomi_da(cfg, getattr(ctx, "speakers", None)),
                         privati_da_config(cfg) if cfg is not None else [])
        _, nel_valore = rip.pulisci(testo)
        _, nella_frase = rip.pulisci(t.testo or "")
    except Exception:  # noqa: BLE001 — il controllo non deve rompere la politica
        return []
    return [x for x in nel_valore if x not in nella_frase]


# ─────────────────────────── la matrice (fase 3, § 5.4) ───────────────────────────
VALORE_REGOLE = (
    "valore_lettura", "valore_non_ancorata", "valore_bersaglio_dato", "valore_contenuto_dato",
    "valore_contenuto_non_detto", "valore_dati_personali", "valore_esegue",
    "valore_voce", "valore_e3_chiede", "valore_e4_sfida")


def ancorata(cl, name: str, args: dict, t) -> bool:
    """La frase di questo turno chiede proprio questo tool: le sue parole (Classe.verbi, per
    azione Classe.verbi_azione) non negate; un fatto della persona detto in questa frase
    (ricorda). Senza parole dichiarate: un'azione interna dichiarata (un'estensione d'azione)
    con una richiesta d'azione qualunque; un tool senza classe o una pericolosa mai."""
    if cl.verbi is None and not cl.verbi_azione:
        return (cl.dichiarata and cl.classe == pol.AZIONE
                and pol.chiesta_azione(t.testo))
    return pol.chiesto_con_verbi(cl, t.testo, args) or pol.fatto_detto(cl, args, t)


def _mostra(valore) -> str:
    return pol._corto(_testo(valore) or "", 80)


def decidi_valore(name: str, args: dict, cl, t, base, conferma_voce: bool = False,
                  voce_frase: bool = False, cosa: str | None = None, ctx=None, spec=None,
                  fidati=()) -> tuple:
    """La decisione della politica per valore, accanto a quella di oggi (`base`, da
    politica.decidi): (Decisione, dettagli). Con la conversazione pulita, per le letture, i
    tool vietati, il dato letto in questa risposta, la delega al dato, il «sì» alla domanda e
    l'intenzione confermata vale `base` (lì il progetto non cambia niente)."""
    args = args or {}
    E = effetto(name, args, spec)
    tipi = argomenti_di(name, spec)
    det = {"effetto": NOMI_EFFETTO.get(E, "E3"), "argomenti": {}, "bersagli": []}
    if (t is None or not t.contaminazione or cl.classe in (pol.SICURO, pol.VIETATO)
            or base.esito in ("blocca", "vieta") or base.regola in (
                "politica_delega", "intento_confermato", "consenso_richiesta",
                "politica_fatto_detto")):
        return base, det
    if cl.sola_lettura is not None and pol._s(args, cl.sola_lettura[0]).lower() in cl.sola_lettura[1]:
        return base, det
    if callable(cl.innocua) and base.esito == "esegui" and not base.regola:
        try:
            if cl.innocua(args):
                return base, det
        except Exception:  # noqa: BLE001
            pass
    proposta, _ripetuta, _stessa = pol.consenso_turno(name, args, cl, t)
    if proposta:
        return base, det
    fonte = sorted(t.contaminazione)[0]
    cosa = cosa or pol._cosa(cl, args)
    if E == E0:
        return pol.Decisione("esegui", "valore_lettura"), det
    # 1. l'ancora: chi l'ha chiesta
    if not ancorata(cl, name, args, t):
        if not t.risposta.get("rifiutata_valore"):
            t.risposta["rifiutata_valore"] = True
            return pol.Decisione("rifiuta", "valore_non_ancorata", "", fonte), det
        return pol.Decisione("conferma", "valore_non_ancorata",
                             f"Non me l'hai chiesto: vuoi che {cosa}?", fonte), det
    # 2. da dove vengono gli argomenti
    f = Fonti.da(t, fidati)
    etichette, bers_dato, cont_dato, cont_modello = {}, [], [], []
    for k, v in args.items():
        tipo = (tipi or {}).get(k, BERSAGLIO)
        if tipo == IGNORA:
            continue
        e = etichetta(v, tipo, f)
        # senza tipi dichiarati: un argomento senza fonte vale come preso dal dato (§ 5.2)
        if tipi is None and e == MODELLO:
            e = DATO
        etichette[k] = f"{tipo.partition(':')[0]}/{e}"
        if (tipo == BERSAGLIO or tipo.startswith(INDICE)) and e == DATO:
            bers_dato.append(k)
        elif tipo == CONTENUTO and e == DATO:
            cont_dato.append(k)
        elif tipo == LIBERO and distintive(v, f):
            cont_dato.append(k)
        elif tipo == CONTENUTO and e == MODELLO and prov.parole(_testo(v) or ""):
            cont_modello.append(k)
    det["argomenti"] = etichette
    det["bersagli"] = sorted({etichette[k].split("/")[1] for k in etichette
                              if etichette[k].startswith((BERSAGLIO + "/", INDICE + "/"))})
    if bers_dato:
        k = bers_dato[0]
        domanda = (f"«{_mostra(args[k])}» viene {prov.da(fonte)}, non da te: vuoi davvero che "
                   f"{cosa}?")
        return pol.Decisione("sfida" if E == E4 else "conferma", "valore_bersaglio_dato",
                             domanda, fonte), det
    if cont_dato and E >= E2:
        k = cont_dato[0]
        domanda = (f"«{_mostra(args[k])}» viene {prov.da(fonte)}, non da te: vuoi davvero che "
                   f"{cosa}?")
        return pol.Decisione("sfida" if E == E4 else "conferma", "valore_contenuto_dato",
                             domanda, fonte), det
    if cont_modello and E >= E2:
        return pol.Decisione("sfida" if E == E4 else "conferma", "valore_contenuto_non_detto",
                             f"C'è di mezzo {prov.detta(fonte)}, quindi chiedo a te: vuoi che "
                             f"{cosa}?", fonte), det
    # Dati personali in ciò che esce (D7): il compito di un lavoro, l'esecuzione di codice
    if E >= E3 or name == "delega_lavoro":
        for k, v in args.items():
            tipo = (tipi or {}).get(k, BERSAGLIO)
            if tipo in (LIBERO, CONTENUTO) and personali(v, t, ctx):
                return pol.Decisione("conferma", "valore_dati_personali",
                                     f"Nel lavoro ci sono dati di casa che non hai detto adesso "
                                     f"(«{_mostra(v)}»): vuoi davvero che {cosa}?", fonte), det
    # 3. che effetto ha
    if E == E4:
        return pol.Decisione("sfida", "valore_e4_sfida", "", fonte), det
    if E == E3:
        if voce_frase:
            return pol.Decisione("esegui", "valore_voce"), det
        return pol.Decisione("conferma", "valore_e3_chiede",
                             f"C'è di mezzo {prov.detta(fonte)}, quindi chiedo a te: vuoi che "
                             f"{cosa}?", fonte), det
    return pol.Decisione("esegui", "valore_esegue"), det


def ombra(base, nuova, det: dict) -> dict:
    """Il campo `politica_ombra` della chiamata nel registro dei turni: solo nomi di regole,
    classi ed etichette, nessun valore."""
    return {"vera": base.esito, "vera_regola": base.regola or "", "nuova": nuova.esito,
            "nuova_regola": nuova.regola or "", "effetto": det.get("effetto"),
            "argomenti": dict(det.get("argomenti") or {}),
            "bersagli": list(det.get("bersagli") or [])}


def copia_turno(t):
    """Una copia del turno per la decisione che non vale: il rifiuto leggero della risposta
    (Turno.risposta) non deve contare due volte."""
    return replace(t, risposta=dict(t.risposta)) if t is not None else None
