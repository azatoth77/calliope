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
riconosciuta (il «sì» con la voce, la sfida superata, la richiesta ripetuta), o chiesta da lei
con la voce in questa frase ed eseguita, che poi fallisce resta un'intenzione aperta per quel tool, quel bersaglio e quella persona: la chiamata corretta
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

import json
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
    # la città di casa detta a voce (09/10, calliope/luogo.py)
    "citta_casa_salva": {"citta": B, "conferma": S},
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
    "lavoro_affida": {"tipo": Z, "compito": L, "vincoli": L, "proposta": X, "file": B,
                      "allegato": "indice:allegato", "formato": S, "modello": S},
    "lavoro_annulla": {"quale": Z},
    "programma_esegui": {"lavoro": B, "dati": C},
    "lavoro_rispondi": {"lavoro": B, "risposta": C},
    "modello_compila": {"modello": Z, "dati": C, "proposta": X},
    "anagrafica_salva": {"azione": Z, "nome": B, "dati": C, "proposta": X},
    "conversazioni_dimentica": {},
    "pc_guarda": {"cosa": Z},
    "immagine_archivia": {"foto": "indice:foto", "quale": B},
    "allegato_archivia": {"allegato": "indice:allegato"},
    # 08/10, cassetto dei file: «quale» sceglie i file della persona, «minore» (prima «di», che
    # resta accettato: 17/10, #58) un ragazzo per il suo tutore
    "cassetto_gestisci": {"azione": Z, "quale": B, "minore": B, "ragazzo": B, "di": B},
    # 08/10, cronologia delle schede per persona: senza argomenti, solo quelle di chi parla
    "schede_pulisci": {},
    # 13/10, conversazione di stanza: ferma o riprende l'ascolto della stanza
    "stanza_pausa": {"azione": Z, "minuti": S},
    # 12/10, i dati conservati per le misure: l'azione scelta in un enum, la persona da svuotare
    "dati_conservati": {"azione": Z, "persona": B},
    # 14/10, i conoscenti (decisione 0030): chi è il conoscente (o il familiare) di cui si parla
    "conoscenti": {"azione": Z, "chi": B},
    "conoscente_livello": {"azione": Z, "chi": B, "nascita": C, "tutori": B},
    "richiesta_tutore": {"cosa": Z, "nome": B, "minuti": S},
    "minore_gestisci": {"nome": B, "azione": Z, "valore": C},
    "installa_avvia": {"azione": B},
    "installa_gestisci": {"azione": Z},
    # 08/10 (versione 2): estensioni e programmi si aprono qui (prima estensione_crea e
    # delega_lavoro di codice); tipo sceglie quale, file e allegato come per i lavori
    # «nome»: il nome che il modello dà alla funzione nuova («Meteocittà suggerimenti») è un
    # testo libero come il compito (09/10, caso vero della DGX delle 20:39: come contenuto, la
    # parola «suggerimenti» non detta faceva chiedere «C'è di mezzo una pagina internet…»); si
    # giudica sulle parole distintive prese da un dato
    "sviluppo_apri": {"tipo": Z, "compito": L, "nome": L, "gia_fatto_da": S,
                      "come_chiederlo": L, "proposta": X, "gioco": S, "vincoli": L,
                      # 11/10: «no, tutto insieme» alla proposta a tappe (un sì o no)
                      "tappe": S,
                      "file": B, "allegato": "indice:allegato",
                      # 08/10 (giro 10): l'estensione esistente di cui fare una versione nuova
                      "modifica": B},
    "estensione_gestisci": {"azione": Z, "nome": B, "esecuzione": B, "sempre": S,
                            "titolo": C},
    # 08/10, modalità sviluppo (calliope/sviluppo.py): lo sviluppo è quello aperto di chi parla
    # (il bersaglio non è un argomento); quale sceglie tra i suoi sospesi
    "sviluppo_passo": {"azione": Z, "quale": B, "cambia": L},
    # 12/10: anche `argomenti` (l'oggetto con un valore per input, dal 08/10 sera), che non c'era
    # e valeva bersaglio: un oggetto non ha parole → «dato», e «Prova con Bergamo» con
    # argomenti = {"citta": "Bergamo"} chiedeva ««» viene dal lavoro di un agente, non da te»
    # (casi veri della DGX: le città dette dalla persona). Si giudicano i suoi valori, le
    # chiavi no (OGGETTO_VALORI), come politica.detto_dopo_dato
    "sviluppo_collauda": {"dati": C, "argomenti": C},
    # 08/10 (versione 2): la domanda all'agente che l'ha scritto (sola lettura) e la correzione
    "sviluppo_chiedi": {"domanda": C},
    "sviluppo_correggi": {"problema": L},
}

# Gli argomenti oggetto che si giudicano dai loro valori (stringhe e numeri, non le chiavi)
OGGETTO_VALORI: dict[str, tuple[str, ...]] = {"sviluppo_collauda": ("argomenti",)}

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


def _apri(a: dict) -> int:
    # 08/10 (versione 2): un programma esegue codice dell'agente (E3, come il codice di
    # delega_lavoro); un'estensione prepara solo una versione da approvare (E2)
    t = pol._s(a, "tipo").lower()
    return E3 if t in ("programma", "codice") else E2


def _sviluppo(a: dict) -> int:
    # 08/10: sospendere, riprendere, uscire cambiano solo lo stato dell'iter (E1); tornare
    # all'analisi o promuovere preparano un lavoro dell'agente da confermare (E2); avanti può
    # arrivare all'approvazione, che ha la sua sfida (E3)
    az = pol._s(a, "azione").lower()
    if az in ("sospendi", "riprendi", "chiudi", "esci", "indietro"):
        return E1                            # indietro (12/10): scarta una modifica proposta
    if az in ("analisi", "promuovi", "ferma"):
        return E2                            # ferma: come lavoro_annulla (08/10 sera)
    return E3                                # avanti, rifai, completa (11/10): riparte un lavoro


def _cassetto(a: dict) -> int:
    # 28/10 sera (decisione di chi amministra, seguito della #301): eliminare dal cassetto non si
    # disfa (E3: per iscritto vuole la voce); tenere e tenere ancora restano E2
    az = pol._s(a, "azione").lower()
    return E3 if az in ("elimina", "cancella", "butta") else E2


def _ricorda(a: dict) -> int:
    # D3: per tutti E2; personale E2 anche lui, ma senza parole dal dato si esegue come oggi
    # (fatto_detto o ancorata): la differenza la fanno le etichette
    return E2


EFFETTI: dict[str, object] = {
    # E1: locale, di chi parla o del dispositivo davanti a lei, si disfa con una frase
    "pc_volume": E1, "pc_luminosita": E1, "pc_media": E1, "pc_apri_file": E1,
    "timer_imposta": E1, "promemoria_imposta": E1, "cambia_voce": E1, "documento_crea": E1,
    "documento_modifica": E1, "pc_blocca": E1, "immagine_archivia": E1,
    "allegato_archivia": E1, "cassetto_gestisci": _cassetto,
    # E2: resta, altri lo vedono o cambia le risposte future
    "lista_aggiungi": E2, "lista_togli": E2, "ricorda": _ricorda, "dimentica": E2,
    "citta_casa_salva": E2,
    "appuntamento_aggiungi": E2, "agenda_annulla": E2, "anagrafica_salva": E2,
    "modello_compila": E2, "richiesta_tutore": E2, "lavoro_rispondi": E2,
    "lavoro_annulla": E2, "pc_guarda": E2, "schede_pulisci": E2, "dati_conservati": E3,
    "stanza_pausa": E1,
    # 14/10: dimenticare un conoscente non si disfa; cambiare chi è di famiglia è fiducia
    "conoscenti": E3, "conoscente_livello": E4,
    # E3: esce di casa, esegue codice o non si disfa
    "programma_esegui": E3, "installa_avvia": E3, "installa_gestisci": E3, "pc_apri_app": E3,
    "estensione_gestisci": E3, "conversazioni_dimentica": E3,
    # E4: fiducia e sicurezza fisica
    "registra_utente": E4, "rinomina_interlocutore": E4, "schermo_gestisci": E4,
    "minore_gestisci": E4,
    # dipendono da un argomento
    "casa_comando": _casa, "lavoro_affida": _delega, "sviluppo_passo": _sviluppo,
    "sviluppo_apri": _apri,
    # il collaudo esegue codice (nel container, con la porta stretta)
    "sviluppo_collauda": E3,
    # la domanda all'agente non cambia niente (sola lettura); la correzione rifà il codice
    # dello sviluppo con l'agente (come tornare all'analisi: un lavoro, E2)
    "sviluppo_chiedi": E1, "sviluppo_correggi": E2,
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
        k, fuori, _ = pol.valori_esterni(cl, args or {}, t, name)
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
        # La risposta a una domanda di Calliope fatta con nomi fidati (09/10: «Taverna o Bagno
        # della Taverna?» dai nomi di Home Assistant): quei nomi li ha scelti la persona
        # e la città della casa dalla configurazione (`da_config`, 09/10: fidata come le parole
        # della persona, come per la politica di prima; analisi delle regole § 3.8)
        persona = (f"{t.persona_txt} {getattr(t, 'domanda_fidata', '') or ''} "
                   f"{getattr(t, 'da_config', '') or ''}")
        return cls(prov.parole(t.testo), prov.parole(persona), prov.parole(fid),
                   prov.parole(esterni), _gettoni_numeri(t.testo), _gettoni_numeri(persona),
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
        # Una storpiatura della trascrizione vale come detta (08/10, provenienza.vicina:
        # «Cerno Maggiore» detto, «Cerro Maggiore» nel valore)
        if w in f.frase or prov.vicina(w, f.frase):
            e = DETTO
        elif w in f.persona or prov.vicina(w, f.persona):
            # Detto dalla persona in questa conversazione (un turno di prima, o la risposta a
            # una domanda di Calliope fatta con nomi fidati: Turno.domanda_fidata) vale suo,
            # anche se un dato lo ripete (09/10, casi veri della DGX: «Meteocittà» nominata da
            # Dario più volte e ripetuta negli annunci dell'agente → «viene dal lavoro di un
            # agente, non da te»). Storico (08/10–09/10): per un bersaglio valeva «dato» (il
            # «latte» del 06/10, detto prima e scelto dal dato); resta «dato» solo una parola
            # che sta SOLO nel dato
            e = PERSONA
        elif w in f.dato:
            # Il dato prima del fidato: un valore del dato che un tool interno ha ripetuto
            # (il nome di un timer messo da una pagina) non diventa fidato
            e = DATO
        elif w in f.fidato:
            e = FIDATO
        else:
            # Con una foto le parole senza fonte possono venire dalla foto (lo scontrino, la
            # scritta): per un bersaglio e, dal 09/10 (fase 4), per un contenuto, come
            # politica.valori_esterni (««birra» viene da una foto, non da te»)
            e = DATO if (tipo in (BERSAGLIO, CONTENUTO) and f.foto) else MODELLO
        if peggiore is None or ORDINE[e] > ORDINE[peggiore]:
            peggiore = e
    for n in _gettoni_numeri(testo):
        e = (DETTO if n in f.numeri_frase else PERSONA if n in f.numeri_persona
             else DATO if n in f.numeri_dato else MODELLO)
        if peggiore is None or ORDINE[e] > ORDINE[peggiore]:
            peggiore = e
    return peggiore or SCELTO


def parole_dato(t) -> tuple[set, set]:
    """Le parole e i numeri dei dati non fidati del turno (come `Fonti.dato` e `numeri_dato`)."""
    esterni = " ".join(x for _, x in (getattr(t, "esterni", None) or ()))
    return prov.parole(esterni), _gettoni_numeri(esterni)


def di_prima(name: str, k: str, valore, t, f: Fonti) -> bool:
    """Il valore `valore` dell'argomento `k` è «dal dato» solo per parole o numeri che il modello
    aveva già passato allo stesso tool in questa risposta PRIMA di leggere un dato, e che allora
    non stavano in nessun dato (12/10 sera, prove/prova_sviluppo_giro6_ollama.py: «prova con
    Valfiorita e Borgo Alto» → il primo collaudo con giorni = 3, il risultato «per 3 giorni», il
    secondo collaudo con lo stesso 3 fermato da `valore_contenuto_dato`). È la regola
    `dopo_dato_valore_di_prima` della politica di prima (politica.detto_dopo_dato), che la
    politica per valore non aveva. Solo i tool di politica.DOPO_DATO_SE_DETTO (il collaudo:
    un contenuto, mai un bersaglio) e solo se un dato è stato letto in questa risposta. Un
    numero che c'era già in un dato quando è stato scelto (l'annuncio dell'agente), o che la
    chiamata di prima non aveva, resta dal dato."""
    if k not in (pol.DOPO_DATO_SE_DETTO.get(name) or ()) or t is None or not t.letto_ora:
        return False
    r = t.risposta if isinstance(getattr(t, "risposta", None), dict) else {}
    prima = (r.get("valori_prima") or {}).get(name)
    dp = r.get("dato_prima")
    if not prima or not dp:
        return False
    parole_prima, numeri_prima = set(), set()
    for x in prima:
        parole_prima |= prov.parole(x)
        numeri_prima |= _gettoni_numeri(x)
    testo = _testo(valore) or ""
    nuove = [w for w in prov.parole(testo) if w in f.dato and w not in dp[0]
             and w not in f.frase and w not in f.persona]
    nuovi = [n for n in _gettoni_numeri(testo) if n in f.numeri_dato and n not in dp[1]
             and n not in f.numeri_frase and n not in f.numeri_persona]
    return bool(nuove or nuovi) and all(w in parole_prima for w in nuove)         and all(n in numeri_prima for n in nuovi)


# Gli argomenti che nominano uno sviluppo di chi parla (11/10, DGX delle 15:53: «Fallo continuare
# allora» → sviluppo_passo {azione: avanti, quale: "videogioco a tema Halloween da giocare"}, e
# `quale` era bersaglio/dato perché il titolo stava nell'annuncio del lavoro, scritto dal lavoro
# di un agente: «ESEGUITE con un bersaglio dal dato» = 1). Il titolo di uno sviluppo aperto o
# sospeso della STESSA persona lo ha dato Calliope (sviluppo.Sviluppi, dalla sua richiesta): è
# un bersaglio fidato, come la città di casa (`da_config`). Solo questi argomenti, e solo se
# il valore è l'id o parole del titolo di un suo sviluppo; un titolo di un altro, o che non è
# di nessuno sviluppo, resta quello che era
# 12/10: anche `nome` di estensione_gestisci (S6 del 09/10, 21:00: all'attivazione «Meteocittà
# viene dal lavoro di un agente, non da te», poi la frase di sfida: due domande per la stessa
# azione). Con la voce riconosciuta lo copriva già `sviluppo_intento` in politica.controlla;
# senza (un «sì» breve) la domanda in più restava. L'approvazione chiede comunque la sfida
SVILUPPO_NOMINATO: dict[str, tuple[str, ...]] = {"sviluppo_passo": ("quale",),
                                                 "estensione_gestisci": ("nome",)}


def sviluppo_suo(name: str, k: str, valore, ctx, args: dict | None = None) -> bool:
    """`valore` (l'argomento `k` di `name`) nomina uno sviluppo aperto o sospeso di chi parla:
    il suo id («S3») o parole tutte del suo titolo (o del nome della sua estensione). Per
    estensione_gestisci (12/10) solo approva e rifiuta, e solo l'estensione dello sviluppo
    APERTO (non un sospeso, non le altre azioni: rimuovi, disattiva restano come prima)."""
    if k not in SVILUPPO_NOMINATO.get(name, ()) or ctx is None:
        return False
    if not isinstance(valore, str) or not valore.strip():
        return False
    gestisci = name == "estensione_gestisci"
    if gestisci and pol._s(args or {}, "azione").lower() not in ("approva", "rifiuta"):
        return False
    try:
        from .sviluppo import chi, servizio
        svs, persona = servizio(ctx), chi(ctx)
        if svs is None or persona is None:
            return False
        with svs._lock:
            suoi = [(s.id, f"{s.titolo} {s.estensione or ''}") for s in svs.sviluppi
                    if s.persona == persona and (s.stato == "aperta" if gestisci else
                                                 s.stato in ("aperta", "sospesa"))
                    and (s.estensione or not gestisci)]
    except Exception:  # noqa: BLE001 — nel dubbio resta l'etichetta di prima
        return False
    v = valore.strip().lower()
    if re.fullmatch(r"s\d+", v):
        return any(i.lower() == v for i, _ in suoi)
    pv = prov.parole(valore)
    return bool(pv) and any(pv <= prov.parole(titolo) for _, titolo in suoi)


# Nomi propri, sigle, numeri, indirizzi: le parole «distintive» di un testo libero. Le parole
# comuni che il modello aggiunge espandendo la richiesta («approfondita», «analizzando») non
# contano (§ 5.2: la quota di parole della persona in un compito ha mediana 0,17)
_DISTINTIVA = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+|https?://\S+|www\.\S+|"
                         r"(?<=[^.!?:\s«\"'(]\s)[A-ZÀ-Ý][\wà-ÿ']{2,}|\b[A-Z]{2,}\b|\b\w*\d\w*\b")


def fuori_dai_valori(spec, k: str, valore) -> bool:
    """Il valore di testo `valore` dell'argomento `k` non è tra i valori ammessi (enum) dello
    schema del tool. Senza enum: False."""
    if not isinstance(valore, str) or not valore.strip():
        return False
    try:
        p = ((getattr(spec, "parameters", None) or {}).get("properties") or {}).get(k) or {}
        ammessi = p.get("enum")
    except AttributeError:
        return False
    if not ammessi:
        return False
    return valore.strip().lower() not in {str(a).strip().lower() for a in ammessi}


# Il numero di un elenco puntato che il modello scrive riformulando la richiesta («L'estensione
# deve: 1. Gestire… 2. Classificare…»; 18/10, issue #169, caso vero della DGX delle 14:47: «1»,
# «2», «3» stanno in ogni risultato web, e la descrizione dettata a voce «veniva da una pagina
# internet»). Candidato: in testa al valore o dopo un confine di frase («:», «.», «;», «!», «?»,
# un a capo), con il punto o la parentesi e poi uno spazio; «Via dei Tigli 4. Poi…» o «chiama il
# 3» non lo sono mai. Un candidato è un segno solo se fa parte di una **sequenza in ordine** nello
# stesso valore (1, 2, 3…; revisione della PR #177: «Consegna al piano: 3.», «Suona all'interno:
# 12.», «Il codice del portone è: 47.» sono il valore, non un segno), dopo «:» solo il primo
# della sequenza, e un «1.» da solo solo in testa al valore. Del segno si toglie solo la cifra:
# il punto o la parentesi restano, così la parola dopo vale come prima («4) Ermenegildo» resta
# distintivo, come sul codice di prima)
_SEGNO_ELENCO = re.compile(r"(?:(?<=^)|(?<=[:;.!?\n]\s)|(?<=\n))(\d{1,2})([.)])(?=\s)")


def segni_elenco(testo: str) -> list:
    """I segni d'elenco del testo (già senza spazi in testa): i `re.Match` di `_SEGNO_ELENCO`
    che formano la sequenza 1, 2, 3… (vedi sopra)."""
    presi, atteso = [], 1
    for m in _SEGNO_ELENCO.finditer(testo):
        n = int(m.group(1))
        if n != atteso:
            continue
        dopo_due_punti = m.start() >= 2 and testo[m.start() - 2] == ":"
        if dopo_due_punti and n != 1:
            continue
        presi.append(m)
        atteso += 1
    if len(presi) == 1 and presi[0].start() != 0:
        return []                           # un «1.» da solo dentro il valore non è un elenco
    return presi


def senza_segni_elenco(testo: str) -> str:
    """Il testo con le cifre dei segni dell'elenco puntato tolte (`segni_elenco`): resta il
    punto o la parentesi."""
    t = str(testo or "").lstrip()
    for m in reversed(segni_elenco(t)):
        t = t[:m.start()] + m.group(2) + t[m.end():]
    return t


def distintive(valore, f: Fonti) -> list[str]:
    """Le parole distintive del valore che stanno in un dato non fidato e non nelle parole
    della persona (ora o prima). I numeri di un elenco puntato scritto dal modello non lo sono
    (#169, `_SEGNO_ELENCO`)."""
    testo = senza_segni_elenco(_testo(valore) or "")
    out = []
    for m in _DISTINTIVA.finditer(" " + testo):
        for w in prov.parole(m.group(0)) | _gettoni_numeri(m.group(0)):
            if w in f.persona or w in f.frase or w in f.numeri_frase or w in f.numeri_persona:
                continue
            if prov.vicina(w, f.frase):       # storpiatura della trascrizione (08/10)
                continue
            if w in f.dato or w in f.numeri_dato:
                out.append(w)
    return sorted(set(out))


def personali(valore, t, ctx) -> list[str]:
    """I tipi di dato personale nel valore che la persona non ha detto in questa frase (D7:
    il compito di lavoro_affida, ciò che esce di casa): nomi delle persone di casa, stringhe
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
    "valore_voce", "valore_e3_chiede", "valore_e4_sfida", "valore_consenso_breve",
    "valore_consenso_voce", "valore_consenso_sfida", "valore_sfida_classe",
    "valore_sfida_sospeso")


def solo_dal_dato(valore, f: Fonti) -> set[str]:
    """Le parole e i numeri del valore che stanno in un dato non fidato e non fra quelli della
    persona (detti ora o prima, anche storpiati): quelli che fanno l'etichetta «dato»."""
    testo = _testo(valore) or ""
    out = {w for w in prov.parole(testo) if w in f.dato and w not in f.frase
           and w not in f.persona and not prov.vicina(w, f.frase)
           and not prov.vicina(w, f.persona)}
    out |= {n for n in _gettoni_numeri(testo) if n in f.numeri_dato
            and n not in f.numeri_frase and n not in f.numeri_persona}
    return out


def fonte_del_valore(valore, t, parole: set | None = None) -> str:
    """La fonte del dato non fidato da cui vengono le parole del valore (09/10, analisi delle
    regole § 3.3: prima si diceva la prima fonte in ordine alfabetico, «viene da una foto» per
    un numero della pagina). "" se nessuna (o una foto, che non ha testo).

    `parole`: le sole parole che hanno fatto chiedere (`solo_dal_dato`, o le distintive di un
    testo libero). Dal 18/10 (issue #169, caso vero della DGX delle 14:55) la matrice le passa:
    con tutte le parole del valore vinceva l'ultimo dato con una parola qualunque in comune, e
    il blocco della stanza, che ha anche le frasi di chi parla, «era» la fonte di una
    descrizione dettata a voce. Con le `parole` vince il dato che ne ha di più (a pari numero
    il più recente)."""
    testo = _testo(valore) or ""
    ps = set(parole) if parole else prov.parole(testo) | _gettoni_numeri(testo)
    if not ps:
        return ""
    meglio, quante = "", 0
    for f, txt in reversed(list(getattr(t, "esterni", None) or ())):
        n = len(ps & (prov.parole(txt) | _gettoni_numeri(txt)))
        if n and not parole:
            return f
        if n > quante:
            meglio, quante = f, n
    if meglio:
        return meglio
    return "foto" if "foto" in (getattr(t, "contaminazione", None) or ()) else ""


def consenso_della_persona(ctx) -> bool:
    """Il «sì» viene dalla persona della conversazione: riconosciuta dalla voce in questa
    frase o, per una frase breve, dalla conversazione (ciclo.py: in compagnia una frase breve
    non vale nessuno). Non la zona grigia, non un ospite, non scritto da uno schermo."""
    sc = getattr(ctx, "speaker_ctx", None)
    return (sc is not None and getattr(sc, "current_speaker", None) is not None
            and getattr(sc, "identified_by", None) in ("voce", "breve"))


def ancorata(cl, name: str, args: dict, t) -> bool:
    """La frase di questo turno chiede proprio questo tool: le sue parole (Classe.verbi, per
    azione Classe.verbi_azione) non negate; un fatto della persona detto in questa frase
    (ricorda). Senza parole dichiarate: un'azione interna dichiarata (un'estensione d'azione)
    con una richiesta d'azione qualunque; un tool senza classe o una pericolosa mai."""
    if cl.verbi is None and not cl.verbi_azione:
        return (cl.dichiarata and cl.classe == pol.AZIONE
                and pol.chiesta_azione(t.testo))
    return pol.chiesto_con_verbi(cl, t.testo, args) or pol.fatto_detto(cl, args, t)


# Una data scritta in cifre dal modello (#98, revisione della PR #117): solo per lei il mese
# detto a parole vale anche in cifre, non per un importo o un numero qualunque
_FORMA_DATA = re.compile(r"\s*(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{4})\s*")


# I rinvii valgono come una negazione per la risposta al dato (#98, seconda revisione della PR
# #117): «Rimandiamo, è nata il 12 ottobre 2015», «Più tardi…», «Lascia, …», «Annulliamo…»
# non sono una risposta da eseguire. Vincolo di sicurezza (principio 10): toglie solo l'ancora
_RINVIO = re.compile(
    r"(?<![a-zà-ù])(?:rimand\w*|rinvi\w*|aspett\w*|più tardi|piu tardi|dopo|lascia\w*|"
    r"annull\w*|ferm\w*|domani|dopodomani|ci penso|ci pensiamo|vediamo|controll\w*|"
    r"forse)(?![a-zà-ù])", re.I)


def forma_data(valore) -> bool:
    return isinstance(valore, str) and bool(_FORMA_DATA.fullmatch(valore))


def _esatto(valore) -> str:
    """Un valore normalizzato per il confronto esatto con la domanda (#98, revisione della PR
    #117: `pol._uguali` guarda solo le parole lunghe, e «non spegnere il server» valeva come
    «spegnere il server», «10 euro» come «900 euro»): maiuscole e spazi soltanto."""
    if isinstance(valore, str):
        return " ".join(valore.split()).casefold()
    try:
        return json.dumps(valore, ensure_ascii=False, sort_keys=True).casefold()
    except (TypeError, ValueError):
        return repr(valore)


def _numeri_mesi(testo) -> set[str]:
    """Il numero dei mesi detti a parole («12 ottobre 2015» → «10»): il modello può scrivere
    la data come «2015-10-12»."""
    from .testi import MESI
    return {str(MESI.index(g) + 1) for g in pol._gettoni(testo) if g in MESI}


def risposta_al_sospeso(name: str, args: dict, t) -> bool:
    """La chiamata è la risposta della persona alla domanda in sospeso di questo stesso tool
    (16/10, issue #98, caso vero della DGX del 15/10 alle 19:58: «Quando è nata Bianca?» di
    registra_utente, la data detta da chi amministra con la stanza accesa → `valore_non_ancorata`,
    «la persona non ha chiesto azioni»). Il tool ha chiesto un dato e la persona lo dà: la
    richiesta è quella di prima. Vale solo se:

    - la domanda in sospeso è di questo tool (Turno.in_sospeso: la stessa persona e il tempo li
      controlla già Brain._take_pending), senza foto o file arrivati con la frase, e non è una
      domanda della politica («Non me l'hai chiesto: vuoi che…?» vuole un consenso, non un dato);
    - la frase non ha una negazione né un «aspetta», «lascia perdere» (`pol._NO`: «No, aspetta,
      non registrarla: forse è nata il 12 ottobre…» non è una risposta da eseguire);
    - la proposta dichiara quali argomenti chiede (`in_sospeso["chiede"]`, Turno.chiede_sospeso):
      solo quelli possono essere nuovi, almeno uno c'è, e gli argomenti della domanda restano
      uguali **esatti** (maiuscole e spazi a parte); nessun altro argomento in più;
    - ogni valore nuovo è detto in questa frase (parole e numeri; il mese a parole vale anche in
      cifre solo per un valore con la forma di una data), non preso da una riga della stanza o
      da un altro dato: un valore senza parole (un booleano, una scelta) non basta.

    Revisione di sicurezza della PR #117 (16/10): confronto esatto, negazione, argomenti
    dichiarati, mese solo per le date.

    Vincolo di permesso su una chiamata già scelta dal modello (principio 10): allarga l'ancora,
    il resto della politica per valore (bersagli dal dato, effetto) resta."""
    if not pol._proposta(t, name) or getattr(t, "sospeso_politica", False):
        return False
    if pol._NO.search(t.testo or "") or _RINVIO.search(t.testo or ""):
        return False
    sosp = t.args_sospeso
    chiede = set(getattr(t, "chiede_sospeso", None) or ())
    if not isinstance(sosp, dict) or not chiede:
        return False
    args = args or {}
    for k, v in sosp.items():
        if k not in args or _esatto(args[k]) != _esatto(v):
            return False
    nuovi = {k: v for k, v in args.items() if k not in sosp and v not in (None, "", False)}
    if not nuovi or not set(nuovi) <= chiede:
        return False
    f = Fonti.da(t)
    f_data = replace(f, numeri_frase=f.numeri_frase | _numeri_mesi(t.testo))
    for v in nuovi.values():
        if _testo(v) in (None, "") or etichetta(
                v, CONTENUTO, f_data if forma_data(v) else f) != DETTO:
            return False
        # Una data in cifre deve essere proprio quella detta (giorno, mese, anno), non averne
        # solo i pezzi: «2015-12-10» dopo «12 ottobre 2015» no (seconda revisione della PR #117)
        if forma_data(v):
            from .minori import leggi_data
            detta = leggi_data(t.testo or "")
            if detta is None or leggi_data(v) != detta:
                return False
    return True


def _mostra(valore) -> str:
    testo = _testo(valore)
    if testo is None:
        # un oggetto (gli argomenti del collaudo, 12/10): i suoi valori, non ««»»
        testo = " ".join(pol._valori_foglia(valore))
    return pol._corto(testo or "", 80)


def decidi_valore(name: str, args: dict, cl, t, base, conferma_voce: bool = False,
                  voce_frase: bool = False, cosa: str | None = None, ctx=None, spec=None,
                  fidati=()) -> tuple:
    """La decisione della politica per valore (`_matrice`), con la frase di sfida dichiarata
    nella classe come pavimento (09/10, analisi delle regole § 3.8: `installa_avvia` ha
    `sfida=True` ma è E3, e con la voce riconosciuta in questa frase la matrice lo eseguiva
    senza sfida). Una decisione della matrice che esegue o chiede soltanto, per un tool con
    `Classe.sfida`, diventa la sfida (regola `valore_sfida_classe`), salvo la sfida già superata
    in questo turno. Quando vale `base` (la politica di prima) decide lei, come sempre."""
    d, det = _matrice(name, args, cl, t, base, conferma_voce, voce_frase, cosa, ctx, spec,
                      fidati)
    if (d is not base and cl.sfida and d.esito in ("esegui", "conferma")
            and not getattr(t, "sfida", False)
            and not (d.esito == "esegui" and det.get("sfida_portata"))):
        d = pol.Decisione("sfida", "valore_sfida_classe", d.domanda, d.fonte)
    return d, det


def _matrice(name: str, args: dict, cl, t, base, conferma_voce: bool = False,
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
                # la rinomina detta per intero con il verbo (08/10): resta senza domanda
                # anche con la politica nuova (analisi delle regole § 3.8)
                "politica_fatto_detto", "politica_valore_detto")):
        return base, det
    if cl.sola_lettura is not None and pol._s(args, cl.sola_lettura[0]).lower() in cl.sola_lettura[1]:
        return base, det
    if callable(cl.innocua) and base.esito == "esegui" and not base.regola:
        try:
            if cl.innocua(args):
                return base, det
        except Exception:  # noqa: BLE001
            pass
    proposta, _ripetuta, stessa = pol.consenso_turno(name, args, cl, t)
    fonte = pol.fonte_principale(t)
    cosa = cosa or pol._cosa(cl, args)
    # La risposta al dato chiesto dal tool stesso (#98) passa dall'ancora anche se comincia con
    # un consenso («Sì, è nata il 12 ottobre»): il «sì» non è alla domanda della politica
    risposta = risposta_al_sospeso(name, args, t)
    if proposta and not risposta:
        # Il «sì» breve della persona della conversazione a una domanda su un'azione E1–E2
        # (09/10, caso vero della DGX delle 20:39: «Sì.» a «vuoi che spenga la luce della
        # taverna?» → «C'è di mezzo una pagina internet… ripeti: …»). La frase di sfida della
        # politica di prima serve all'identità per le azioni che contano; qui la domanda era
        # sull'intento, e la stessa azione chiesta con le sue parole si sarebbe eseguita
        # senza domande. Mai per i tool con la sfida, per E3–E4, per un ospite o uno scritto
        if (base.esito == "sfida" and base.regola == "politica_sfida" and not cl.sfida
                and E <= E2 and consenso_della_persona(ctx)):
            return pol.Decisione("esegui", "valore_consenso_breve", accettata=stessa), det
        # Il «sì» a una domanda della politica (la stessa chiamata): lo giudica la politica
        # nuova anche per E3–E4 (09/10, analisi delle regole § 3.2). E3: la voce riconosciuta in
        # questa frase (o la sfida superata) basta; altrimenti la frase di sfida, dicendo la
        # causa vera (la voce, non la pagina). E4: sempre la sfida. I tool con la sfida nella
        # classe: il pavimento di decidi_valore
        if getattr(t, "sospeso_politica", False) and stessa and not cl.sfida:
            if E == E3:
                if voce_frase or t.sfida:
                    return pol.Decisione("esegui", "valore_consenso_voce", accettata=True), det
                return pol.Decisione("sfida", "valore_consenso_sfida",
                                     f"{pol.VOCE_INCERTA}: vuoi che {cosa}?", fonte), det
            if E >= E4 and not t.sfida:
                return pol.Decisione("sfida", "valore_e4_sfida", "", fonte), det
        return base, det
    if E == E0:
        return pol.Decisione("esegui", "valore_lettura"), det
    # 1. l'ancora: chi l'ha chiesta (o la risposta al dato chiesto dal tool stesso: #98)
    if risposta:
        det["risposta_sospeso"] = True
        # La frase di sfida superata dalla stessa persona nella frase che ha aperto questa
        # domanda vale anche per la risposta, se la voce di questa frase è la sua (#98: prima
        # una seconda sfida a pochi secondi dalla prima)
        # Una chiamata sola (revisione della PR #117): non i giri di correzione dopo
        if (getattr(t, "sfida_sospeso", False) and voce_frase
                and not t.risposta.get("sfida_portata_usata")):
            det["sfida_portata"] = True
    if not risposta and not ancorata(cl, name, args, t):
        if not t.risposta.get("rifiutata_valore"):
            t.risposta["rifiutata_valore"] = True
            return pol.Decisione("rifiuta", "valore_non_ancorata", "", fonte), det
        return pol.Decisione("conferma", "valore_non_ancorata",
                             f"Non me l'hai chiesto: vuoi che {cosa}?", fonte), det
    # 2. da dove vengono gli argomenti
    f = Fonti.da(t, fidati)
    # la data detta col mese a parole e scritta dal modello in cifre (#98), solo per un valore
    # con la forma di una data
    f_data = replace(f, numeri_frase=f.numeri_frase | _numeri_mesi(t.testo)) if risposta else f
    etichette, bers_dato, cont_dato, cont_modello = {}, [], [], []
    for k, v in args.items():
        tipo = (tipi or {}).get(k, BERSAGLIO)
        if tipo == IGNORA:
            continue
        # Una «scelta» fuori dai valori ammessi dello schema non è una scelta (09/10, fase 4:
        # il modello scrive un testo dove lo schema vuole un enum, e il tool decide da sé):
        # vale come contenuto, con l'etichetta delle sue parole
        if tipo in (AZIONE, SCELTA) and fuori_dai_valori(spec, k, v):
            tipo = CONTENUTO
        if k in OGGETTO_VALORI.get(name, ()):
            v = " ".join(pol._valori_foglia(v)) if pol._valori_foglia(v) else v
        e = etichetta(v, tipo, f_data if forma_data(v) else f)
        # Un valore della chiamata di prima allo stesso tool, scelto prima del dato letto ora
        # (12/10 sera): l'etichetta che aveva allora, con i soli dati di allora
        if e == DATO and di_prima(name, k, v, t, f):
            dp = t.risposta["dato_prima"]
            e = etichetta(v, tipo, replace(f, dato=dp[0], numeri_dato=dp[1]))
            det.setdefault("di_prima", []).append(k)
        # senza tipi dichiarati: un argomento senza fonte vale come preso dal dato (§ 5.2)
        if tipi is None and e == MODELLO:
            e = DATO
        if e in (DATO, MODELLO) and sviluppo_suo(name, k, v, ctx, args):
            e = FIDATO
        etichette[k] = f"{tipo.partition(':')[0]}/{e}"
        if (tipo == BERSAGLIO or tipo.startswith(INDICE)) and e == DATO:
            bers_dato.append(k)
        elif tipo == CONTENUTO and e == DATO:
            cont_dato.append(k)
        elif tipo == LIBERO and distintive(v, f):
            cont_dato.append(k)
        # (anche i soli numeri, 09/10: «eseguilo di nuovo» con dati 7 e 9 che nessuno ha detto)
        elif tipo == CONTENUTO and e == MODELLO:
            cont_modello.append(k)
    det["argomenti"] = etichette
    det["bersagli"] = sorted({etichette[k].split("/")[1] for k in etichette
                              if etichette[k].startswith((BERSAGLIO + "/", INDICE + "/"))})
    # La fonte detta nella domanda: quella delle parole che fanno chiedere (#169)
    def _da(k):
        v = args[k]
        if k in OGGETTO_VALORI.get(name, ()):
            v = " ".join(pol._valori_foglia(v)) if pol._valori_foglia(v) else v
        tipo = (tipi or {}).get(k, BERSAGLIO)
        ps = set(distintive(v, f)) if tipo == LIBERO else solo_dal_dato(v, f)
        if not ps and f.foto and tipo in (BERSAGLIO, CONTENUTO) and _testo(v):
            return "foto"          # parole senza fonte con una foto di mezzo (etichetta)
        return fonte_del_valore(v, t, ps) or fonte

    if bers_dato:
        k = bers_dato[0]
        da = _da(k)
        domanda = (f"«{_mostra(args[k])}» viene {prov.da(da)}, non da te: vuoi davvero che "
                   f"{cosa}?")
        return pol.Decisione("sfida" if E == E4 else "conferma", "valore_bersaglio_dato",
                             domanda, da), det
    if cont_dato and E >= E2:
        k = cont_dato[0]
        da = _da(k)
        domanda = (f"«{_mostra(args[k])}» viene {prov.da(da)}, non da te: vuoi davvero che "
                   f"{cosa}?")
        return pol.Decisione("sfida" if E == E4 else "conferma", "valore_contenuto_dato",
                             domanda, da), det
    if cont_modello and E >= E2:
        return pol.Decisione("sfida" if E == E4 else "conferma", "valore_contenuto_non_detto",
                             f"C'è di mezzo {prov.detta(fonte)}, quindi chiedo a te: vuoi che "
                             f"{cosa}?", fonte), det
    # Dati personali in ciò che esce (D7): il compito di un lavoro, l'esecuzione di codice.
    # Non per la risposta al dato chiesto dal tool (#98): i valori nuovi sono detti in questa
    # frase (anche se scritti in un'altra forma, «12 ottobre 2015» → «2015-10-12»), gli altri
    # sono quelli della domanda
    if (E >= E3 or name in ("lavoro_affida", "sviluppo_apri")) and not risposta:
        for k, v in args.items():
            tipo = (tipi or {}).get(k, BERSAGLIO)
            if tipo in (LIBERO, CONTENUTO) and personali(v, t, ctx):
                return pol.Decisione("conferma", "valore_dati_personali",
                                     f"Nel lavoro ci sono dati di casa che non hai detto adesso "
                                     f"(«{_mostra(v)}»): vuoi davvero che {cosa}?", fonte), det
    # 3. che effetto ha
    if det.get("sfida_portata") and E >= E3:
        t.risposta["sfida_portata_usata"] = True
        return pol.Decisione("esegui", "valore_sfida_sospeso"), det
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
