"""
L'evento e l'elenco chiuso dei tipi (10/10/2026, § 2.1, § 2.2 e § 2.4 del progetto
docs/ricerche/2026-10-10-registro-eventi.md).

Ogni evento ha una **visibilità decisa alla scrittura** (§ 11.1): `modello` (entra nel contesto),
`turno` (solo nel prompt del turno in cui è nato), `schermo` (solo per gli schermi), `registro`
(solo per il rigioco e la diagnosi), `mai` (niente testo, neanche su disco). La proiezione del
contesto ammette per costruzione solo `modello` e, nel loro turno, `turno`.

Su disco (`per_disco`) va una copia dei dati già filtrata: mai foto né allegati, mai il testo dei
dati non fidati, mai le parole della frase di sfida, mai i risultati riservati (§ 2.4). I campi
elencati in `dati["_non_su_disco"]` restano solo in memoria (il testo di un minore fermato dal
guardiano, per esempio).

Solo libreria standard.
"""
from __future__ import annotations

import dataclasses
import json

# Versione dei dati dei tipi (rigioco dei registri vecchi)
VERSIONE = 1

VIS = ("modello", "turno", "schermo", "registro", "mai")


@dataclasses.dataclass(frozen=True)
class Tipo:
    nome: str
    campi: tuple[str, ...]
    vis: str                      # visibilità predefinita
    nota: str = ""


def _t(nome, campi, vis, nota=""):
    return nome, Tipo(nome, tuple(campi.split()), vis, nota)


# L'elenco chiuso (§ 2.2). Un tipo nuovo: ricetta del § 10 (qui, poi PROIEZIONE_CONTESTO e
# PROIEZIONE_TURNI in proiezioni.py, chi lo scrive, una prova prova_eventi_*)
TIPI: dict[str, Tipo] = dict([
    _t("conversazione_aperta", "chiave owner come luogo riassunto riassunto_tipo", "modello",
       "ripresa e coda sono il loro testo, non un riferimento"),
    _t("conversazione_chiusa", "motivo", "registro",
       "dopo, nessun evento con lo stesso conv"),
    _t("detto_persona", "testo canale come sicurezza satellite sfida brain incerte "
                        "riassegnato_da compagnia chi stanza dati", "modello",
       "il testo della sfida non si scrive; chi (il nome di chi l'ha detta nella conversazione "
       "anonima) e stanza (i pezzi della stanza legati alla frase, solo in memoria) dal 15/10; "
       "dati (i dati fissi legati alla frase, solo in memoria) dal 16/10"),
    _t("trascrizione_capita", "prima dopo accettata", "modello",
       "la proiezione usa «dopo» solo se accettata"),
    _t("dato_in_ingresso", "fonte testo caratteri", "modello",
       "su disco solo fonte e caratteri"),
    _t("foto_in_ingresso", "testo numeri fonte", "modello",
       "solo il riferimento (etichetta e numeri nell'album), mai i byte"),
    _t("allegato_in_ingresso", "testo info numeri fonte", "modello",
       "solo il riferimento (numeri nell'album, tipo e dimensione), mai il contenuto"),
    _t("dati_del_turno", "blocchi", "turno", "su disco solo nomi e lunghezze"),
    _t("passata_modello", "n spinta testo trattenuto chiamate", "registro",
       "per il rigioco e la diagnosi"),
    _t("chiamata_tool", "id nome argomenti passata origine", "modello"),
    _t("esito_tool", "id nome ok contenuto riservato personale non_fidato correggibile "
                     "frase in_sospeso fonte resta", "modello",
       "visibilità per tipo di tool decisa alla scrittura (§ 11.1): riservato, personale, "
       "non_fidato e la fonte della busta"),
    _t("detto_calliope", "testo autore atto frase canale satellite fonte dopo_chiamate",
       "modello", "nasce all'invio nell'uscita unica (§ 3.2); dopo_chiamate: quante chiamate "
                  "dei tool c'erano già nella risposta (la posizione fra le frasi)"),
    _t("voce_fine", "da inviate sentite interrotta parziale", "modello",
       "quante frasi del pezzo si sono sentite per intero"),
    _t("interruzione", "seme durante", "registro"),
    _t("proposta_aperta", "id tool argomenti domanda cosa origine effetto tipo chi satellite "
                          "scade turni", "registro", "stato della macchina, non storia"),
    _t("proposta_chiusa", "id come eseguita", "registro",
       "ogni chiusura ha il suo nome"),
    _t("sfida_chiesta", "proposta tentativi", "mai", "le parole della sfida mai su disco"),
    _t("sfida_esito", "proposta esito", "registro"),
    _t("modulo_compilato", "modulo campi titolo", "modello", "solo i nomi dei campi"),
    _t("turno_escluso", "escluso motivo", "registro", "la proiezione salta tutto il turno"),
    _t("compressione", "fino_a riassunto dati usato", "modello"),
    _t("scheda_mandata", "tipo chiave titolo schermi", "schermo",
       "il contenuto resta nella cronologia degli schermi"),
    _t("turno_riassegnato", "da_registro seq a_registro motivo", "registro",
       "mai riscrittura (§ 2.6 c)"),
    _t("turno_chiuso", "esito regole tempi contesto controlli", "registro",
       "sorgente del registro dei turni"),
    # Gli argomenti della conversazione (§ 13, passo 3): li decide il modello (tool `argomento`)
    _t("argomento_nuovo", "id titolo ora motivo prima da_parte", "modello",
       "da qui il turno e i seguenti sono dell'argomento nuovo; `da_parte`: ciò che era aperto "
       "nell'argomento lasciato (sviluppo in pausa, proposta scaduta)"),
    _t("argomento_ripreso", "id titolo ora motivo prima da_parte ripresi", "modello",
       "un argomento messo da parte torna corrente (si annulla anche così un cambio sbagliato)"),
])

# Tre categorie del parlato (§ 2.2, § 4): l'autore di detto_calliope
AUTORI = ("contenuto", "atto", "esito")

# Gli atti: chi, nel ciclo, manda una frase alla voce (passo 2, l'uscita unica: lo dice chi
# chiama `Uscita.di`, non più la funzione del ciclo ricavata dalla pila). Elenco chiuso: un atto
# nuovo si aggiunge qui, con la sua categoria (prova_uscita_unica controlla che ogni atto scritto
# nel codice ci sia). Categorie:
# - `risposta`: parole della risposta (contenuto del modello, frase pronta di un tool, ripiego
#   di Brain), che oggi la storia ha;
# - `registrato`: atto del ciclo che oggi entra nella storia (`record_courtesy`,
#   `record_announcement`);
# - `fuori_storia`: sentito in una conversazione viva, oggi la storia non lo sa (§ 1.1: il
#   motivo `non_in_storia:<atto>` è atteso, e sparisce al passo 3);
# - `voluto`: fuori dalla conversazione per scelta (frasi d'attesa, saluto dell'avvio, giochi,
#   chiusure; decisione di Dario del 10/10).
# Ogni voce: (categoria, annuncio fra un turno e l'altro, riga del § 1.1 del progetto)
CATEGORIE_ATTO = ("risposta", "registrato", "fuori_storia", "voluto")
ATTI: dict[str, tuple[str, bool, str]] = {
    "risposta": ("risposta", False, "1"),
    "ripeti": ("risposta", False, "1c"),
    # La frase onesta al posto di una nota dichiarata due volte senza tool (12/10 sera)
    "onesta": ("risposta", False, "1c"),
    # La frase pronta dopo una risposta che girava in tondo (14/10 notte, ciclo_ripetuto)
    "incartata": ("risposta", False, "1c"),
    # La frase del codice al posto di una frase del modello che diceva la soluzione di un
    # esercizio guidato (31/10, #278, la guardia di Brain)
    "esercizio_svelato": ("risposta", False, "1c"),
    "riga_sviluppo": ("risposta", False, "1f"),
    "sfida": ("risposta", False, "1g"),
    # La mezza frase fissa al cambio d'argomento (§ 13, passo 3): «Metto da parte lo sviluppo
    # di …», detta da Brain dentro la risposta
    "argomento_da_parte": ("risposta", False, "§ 13"),
    "protezione_risposta": ("risposta", False, "1"),
    "cortesia": ("registrato", False, "3"),
    "protezione_cancello": ("registrato", False, "4"),
    "richiesta_tutore": ("registrato", True, "5"),
    "annuncio_documento": ("registrato", True, "6"),
    "annuncio_installazione": ("registrato", True, "6"),
    "annuncio_lavoro": ("registrato", True, "6"),
    "annuncio_estensione": ("registrato", True, "6"),
    "annuncio_cassetto": ("registrato", True, "7"),
    "modulo": ("registrato", False, "8"),
    # La conferma del tool di un tocco dallo schermo (28/10, revisione della PR #261): nella
    # storia, mai alla voce (canale «muta»)
    "tocco_esito": ("registrato", False, "tocco"),
    "annuncio_agenda": ("fuori_storia", True, "10"),
    "avviso_tutore": ("fuori_storia", True, "11"),
    "errore": ("fuori_storia", False, "12"),
    "registrazione": ("fuori_storia", False, "13, 14"),
    "saluto": ("fuori_storia", False, "15"),
    "chi_parla": ("fuori_storia", False, "16"),
    "senza_domanda": ("fuori_storia", False, "17"),
    "protezione": ("fuori_storia", False, "18"),
    "fuori_orario": ("fuori_storia", False, "18"),
    "attesa_tool": ("voluto", False, "2"),
    "attesa_correzione": ("voluto", False, "2"),
    "attesa_coda": ("voluto", False, "2"),
    "attesa_contesto": ("voluto", False, "2"),
    "attesa_biblioteca": ("voluto", False, "2"),
    "attesa_stt": ("voluto", False, "2"),
    # La ricerca nella conversazione della stanza che aspetta le righe in coda (14/10,
    # stanza_cerca, passo 4: frase `attesa.stanza` di frasi.py)
    "attesa_stanza": ("voluto", False, "2"),
    "annuncio_gioco": ("voluto", True, "19"),
    # Le domande standard su un gioco (14/10, gioco_stato.py: «a chi tocca?»), risposte dal
    # codice con l'istantanea; e la mossa capita dal giudice di fase, detta con l'etichetta
    "gioco_stato": ("fuori_storia", False, "22"),
    "gioco_mossa": ("fuori_storia", False, "22"),
    "chiusura": ("voluto", False, "20"),
    "saluto_avvio": ("voluto", False, "21"),
    # I nomi del passo 1 (ricavati dalla pila), per il rigioco degli eventi già su disco
    "attesa": ("voluto", False, "2"),
    "giochi": ("voluto", True, "19"),
    "annuncio": ("registrato", True, "6"),
    "agenda": ("fuori_storia", True, "10"),
    "cassetto": ("registrato", True, "7"),
}
ATTI_PASSO_1 = frozenset({"attesa", "giochi", "annuncio", "agenda", "cassetto"})


def atti_di(categoria: str) -> frozenset:
    return frozenset(n for n, (c, _a, _r) in ATTI.items() if c == categoria)


def categoria(atto) -> str | None:
    v = ATTI.get(atto)
    return v[0] if v else None


def e_annuncio(atto) -> bool:
    v = ATTI.get(atto)
    return bool(v and v[1])
# Canali di ciò che dice Calliope e di ciò che dice la persona
CANALI_CALLIOPE = ("voce", "scritto", "muta")
# «tocco» (28/10, schermi/tocchi.py): un tocco dallo schermo personale che cambia qualcosa
CANALI_PERSONA = ("voce", "scritto", "modulo", "tocco")


@dataclasses.dataclass(frozen=True)
class Evento:
    registro: str        # persona:<id> | ospite:<corsia>
    seq: int             # 1, 2, 3… dentro il registro, senza buchi
    conv: str            # il segmento: id della conversazione (nuovo a ogni apertura)
    corsia: str | None   # il canale da cui è arrivato o verso cui è andato
    t: float             # time.time() di quando è stato scritto
    tipo: str            # dall'elenco chiuso TIPI
    turno: int           # numero della risposta (Conversazione.turn_number)
    vis: str             # visibilità decisa alla scrittura
    dati: dict           # i campi del tipo; solo JSON
    v: int = VERSIONE


class EventoNonValido(ValueError):
    pass


def controlla(tipo: str, vis: str | None, dati: dict) -> str:
    """La visibilità dell'evento (la predefinita del tipo se `vis` è None), o
    EventoNonValido: tipo fuori dall'elenco, visibilità sconosciuta, campi non del tipo."""
    t = TIPI.get(tipo)
    if t is None:
        raise EventoNonValido(f"tipo di evento sconosciuto: {tipo!r}")
    v = t.vis if vis is None else vis
    if v not in VIS:
        raise EventoNonValido(f"visibilità sconosciuta: {v!r}")
    extra = set(dati) - set(t.campi) - {"_non_su_disco", "migrato"}
    if extra:
        raise EventoNonValido(f"campi non previsti per {tipo}: {sorted(extra)}")
    return v


# ─────────────────────────── su disco (§ 2.4) ───────────────────────────
TRACCIA_RISERVATA = {"nota": "risultato riservato: non conservato"}
# La traccia di un risultato riservato nel contesto del modello (la stessa di Brain._seal_private,
# brain._PRIVATE_TRACE: Brain la passa alla proiezione, qui il valore per il disco e le prove)
TRACCIA_PRIVATA = ("Risultato riservato, tolto dalla conversazione dopo la risposta: se serve di "
                   "nuovo, richiama il tool.")


def esito_ok(res) -> bool:
    """Un risultato di tool è riuscito (come brain._result_ok)."""
    return isinstance(res, dict) and "errore" not in res and res.get("ok") is not False


def frase_esito(res) -> str:
    """La frase pronta di un risultato (come brain._result_text)."""
    if not isinstance(res, dict):
        return ""
    for k in ("conferma", "risposta_finale", "da_dire"):
        v = res.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def sigillato(contenuto: str, riservato: bool, personale: bool,
              traccia: str = TRACCIA_PRIVATA) -> str:
    """Il risultato di un tool riservato o personale dopo la risposta (passo 3: la forma di
    Brain._seal_private, decisa dai campi dell'evento scritti alla scrittura): i riservati una
    traccia neutra, i personali la sola frase già pronta; un personale fallito resta com'è.
    Puro."""
    if not riservato and not personale:
        return contenuto
    try:
        res = json.loads(contenuto or "{}")
    except (ValueError, TypeError):
        res = {}
    res = res if isinstance(res, dict) else {}
    ok = esito_ok(res)
    if not ok and not riservato:
        return contenuto
    detta = "" if riservato else frase_esito(res)
    return json.dumps({"ok": ok, **({"conferma": detta} if detta else {"nota": traccia})},
                      ensure_ascii=False)


# I campi con le parole di ogni tipo (12/10, calliope/conserva.py): in un turno le cui parole non
# si conservano (zona grigia; dal 12 al 16/10 anche il dubbio con un minore) restano solo in
# memoria (`_non_su_disco`), come il testo di un minore fermato dal guardiano
CAMPI_TESTO: dict[str, tuple[str, ...]] = {
    "detto_persona": ("testo", "chi"), "trascrizione_capita": ("prima", "dopo"),
    "dato_in_ingresso": ("testo",), "foto_in_ingresso": ("testo",),
    "allegato_in_ingresso": ("testo", "info"), "chiamata_tool": ("argomenti",),
    "esito_tool": ("contenuto", "frase"), "detto_calliope": ("testo",),
    "passata_modello": ("testo",), "proposta_aperta": ("argomenti", "domanda", "cosa"),
    "compressione": ("riassunto",), "scheda_mandata": ("titolo",),
    "argomento_nuovo": ("titolo",), "argomento_ripreso": ("titolo",),
    "modulo_compilato": ("titolo",),
}


def senza_parole(tipo: str, dati: dict) -> dict:
    """I dati con le parole del tipo segnate `_non_su_disco` (in memoria restano)."""
    campi = [c for c in CAMPI_TESTO.get(tipo, ()) if c in dati]
    if not campi:
        return dati
    prima = list(dati.get("_non_su_disco") or ())
    return {**dati, "_non_su_disco": prima + [c for c in campi if c not in prima]}


def per_disco(ev: Evento) -> dict:
    """I dati dell'evento come vanno su disco: senza ciò che non deve restarci. Puro."""
    if ev.vis == "mai":
        return {}
    d = dict(ev.dati)
    for k in d.pop("_non_su_disco", ()) or ():
        d.pop(k, None)
    tipo = ev.tipo
    if tipo == "detto_persona" and d.get("sfida"):
        d.pop("testo", None)                       # le parole della sfida mai
    elif tipo == "dato_in_ingresso":
        testo = d.pop("testo", None)
        d.setdefault("caratteri", len(testo or ""))
    elif tipo in ("foto_in_ingresso", "allegato_in_ingresso"):
        testo = d.pop("testo", None)
        d["caratteri"] = len(testo or "")
    elif tipo == "passata_modello":
        # Il testo generato e non detto (dopo un'interruzione) resta in memoria: su disco la
        # lunghezza
        testo = d.pop("testo", None)
        d["caratteri"] = len(testo or "")
    elif tipo == "dati_del_turno":
        # Il testo dei blocchi (ricordi, contesto) non c'è nemmeno in memoria (12/10): il nome e
        # quanti caratteri; se un blocco ha il testo, su disco la sua lunghezza
        d["blocchi"] = [{"nome": b.get("nome"),
                         "caratteri": (len(b["testo"]) if isinstance(b.get("testo"), str)
                                       else int(b.get("caratteri") or 0))}
                        for b in d.get("blocchi") or () if isinstance(b, dict)]
    elif tipo == "esito_tool":
        if d.get("riservato"):
            d["contenuto"] = json.dumps(TRACCIA_RISERVATA, ensure_ascii=False)
        elif d.get("personale"):
            # Su disco come nel contesto dopo la risposta (passo 3: la storia non è più
            # sigillata a mano prima di arrivare qui): la sola frase pronta
            d["contenuto"] = sigillato(str(d.get("contenuto") or ""), False, True)
        elif d.get("non_fidato"):
            d["contenuto"] = json.dumps({"caratteri": len(str(d.get("contenuto") or ""))},
                                        ensure_ascii=False)
    elif tipo == "sfida_chiesta":
        d.pop("parole", None)
    return d


def riga(ev: Evento) -> tuple:
    """La riga della tabella `eventi` (§ 2.3): registro, seq, conv, corsia, t, tipo, turno, vis,
    persona, ospite, dati (JSON già filtrato), v."""
    persona = ev.registro.split(":", 1)[1] if ev.registro.startswith("persona:") else None
    ospite = 1 if ev.registro.startswith("ospite:") else 0
    return (ev.registro, ev.seq, ev.conv, ev.corsia, ev.t, ev.tipo, ev.turno, ev.vis, persona,
            ospite, json.dumps(per_disco(ev), ensure_ascii=False, sort_keys=True, default=str),
            ev.v)


def da_riga(r) -> Evento:
    """Un evento riletto dal disco (rigioco). Solleva ValueError su una riga rovinata."""
    registro, seq, conv, corsia, t, tipo, turno, vis, dati, v = r
    d = json.loads(dati)
    if not isinstance(d, dict) or tipo not in TIPI or vis not in VIS:
        raise ValueError("riga dell'evento non valida")
    return Evento(str(registro), int(seq), str(conv), corsia, float(t), str(tipo), int(turno),
                  str(vis), d, int(v or VERSIONE))
