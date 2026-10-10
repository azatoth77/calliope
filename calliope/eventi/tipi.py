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
                        "riassegnato_da compagnia", "modello",
       "il testo della sfida non si scrive"),
    _t("trascrizione_capita", "prima dopo accettata", "modello",
       "la proiezione usa «dopo» solo se accettata"),
    _t("dato_in_ingresso", "fonte testo caratteri", "modello",
       "su disco solo fonte e caratteri"),
    _t("foto_in_ingresso", "testo numeri", "modello", "solo il riferimento, mai i byte"),
    _t("allegato_in_ingresso", "testo info", "modello", "solo il riferimento, mai il contenuto"),
    _t("dati_del_turno", "blocchi", "turno", "su disco solo nomi e lunghezze"),
    _t("passata_modello", "n spinta testo trattenuto chiamate", "registro",
       "per il rigioco e la diagnosi"),
    _t("chiamata_tool", "id nome argomenti passata origine", "modello"),
    _t("esito_tool", "id nome ok contenuto riservato personale non_fidato correggibile "
                     "frase in_sospeso", "modello", "visibilità per tipo di tool (§ 11.1)"),
    _t("detto_calliope", "testo autore atto frase canale satellite fonte", "modello",
       "scritto all'invio (§ 3.2)"),
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
])

# Tre categorie del parlato (§ 2.2, § 4): l'autore di detto_calliope
AUTORI = ("contenuto", "atto", "esito")
# Canali di ciò che dice Calliope e di ciò che dice la persona
CANALI_CALLIOPE = ("voce", "scritto", "muta")
CANALI_PERSONA = ("voce", "scritto", "modulo")


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
    elif tipo == "dati_del_turno":
        d["blocchi"] = [{"nome": b.get("nome"), "caratteri": len(b.get("testo") or "")}
                        for b in d.get("blocchi") or () if isinstance(b, dict)]
    elif tipo == "esito_tool":
        if d.get("riservato"):
            d["contenuto"] = json.dumps(TRACCIA_RISERVATA, ensure_ascii=False)
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
