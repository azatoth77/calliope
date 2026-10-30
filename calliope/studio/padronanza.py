"""
La padronanza per argomento dello Studio (30/10, passo 5, issue #245, epic #251, decisione 0035
punto 32; progetto § 5.5 e decisione 4 del 27/10): una cifra da 0 a 100 per (verifica, argomento),
calcolata **nel codice dai soli tentativi** salvati (`studio_tentativi`), mai dal modello, sempre
detta con la parola. Funzioni pure: il servizio (`servizio.Studio.padronanza`) legge il db.

Le soglie sono quelle iniziali, ragionevoli, da tarare sui tentativi veri in ombra (decisione 4
del 27/10, decisione 0019): si cambiano qui, le prove le leggono da qui.

- esito: giusto 1, con indizio 0,5, sbagliato 0 (`ESITI`);
- tipo: carta 1, esercizio 1, casella della mappa 0,7, interrogazione 1,2, verifica finta 1,5
  (`TIPI`);
- età: il peso si dimezza ogni `MEZZA_VITA_GIORNI` (un tentativo vecchio conta meno);
- calo senza ripasso: la cifra × 0,5^(giorni dall'ultimo tentativo / `CALO_GIORNI`);
- misurata solo con almeno `MIN_TENTATIVI` tentativi in almeno `MIN_GIORNI` giorni: prima «non
  ancora misurata», che non è una lacuna;
- a parole: «la sai» (≥ `LA_SAI`), «quasi» (≥ `QUASI`), «da studiare».

Lo stato d'animo e l'autovalutazione «da 1 a 5» non entrano: non sono su disco (0035 punto 27).
"""

from __future__ import annotations

import datetime

ESITI = {"giusto": 1.0, "indizio": 0.5, "sbagliato": 0.0}
TIPI = {"carta": 1.0, "esercizio": 1.0, "mappa": 0.7, "interrogazione": 1.2,
        "verifica_finta": 1.5}
# Chi ha deciso l'esito: la persona (una carta «la sapevo / no»), il codice (una risposta
# controllata), il tutore. Mai il modello da solo (spunto di Dario del 28/10)
FONTI = ("persona", "codice", "tutore")
MEZZA_VITA_GIORNI = 7.0
CALO_GIORNI = 21.0
MIN_TENTATIVI, MIN_GIORNI = 3, 2
LA_SAI, QUASI = 75, 45
# La misura del giorno per la previsione: solo con almeno metà degli argomenti del piano misurati
MISURATI_PER_LIVELLO = 0.5

LA_SAI_P, QUASI_P, DA_STUDIARE_P, NON_MISURATA_P = (
    "la sai", "quasi", "da studiare", "non ancora misurata")

# L'interruttore `studio_padronanza`
SPENTA, OMBRA, MOSTRATA = "spenta", "ombra", "mostrata"
MODI = (SPENTA, OMBRA, MOSTRATA)
# La fonte delle misure del giorno in `studio_misure`: quella dell'ombra la previsione la ignora
FONTE_MISURA, FONTE_OMBRA = "padronanza", "padronanza_ombra"


def _d(x) -> datetime.date:
    if isinstance(x, datetime.datetime):
        return x.date()
    if isinstance(x, datetime.date):
        return x
    return datetime.date.fromisoformat(str(x)[:10])


def parola(valore) -> str:
    if valore is None:
        return NON_MISURATA_P
    return LA_SAI_P if valore >= LA_SAI else QUASI_P if valore >= QUASI else DA_STUDIARE_P


def calcola(tentativi: list[dict], oggi) -> dict:
    """{argomento: {valore, parola, tentativi, giorni, ultimo}} dai tentativi (`argomento`,
    `giorno`, `tipo`, `esito`). Un tentativo con tipo o esito sconosciuti non conta. `valore` è
    None (e la parola «non ancora misurata») sotto la soglia di misura."""
    oggi = _d(oggi)
    per: dict = {}
    for t in tentativi:
        if t.get("esito") not in ESITI or t.get("tipo") not in TIPI or t.get("argomento") is None:
            continue
        try:
            g = _d(t["giorno"])
        except (TypeError, ValueError):
            continue
        per.setdefault(int(t["argomento"]), []).append((g, t["tipo"], t["esito"]))
    out = {}
    for aid, righe in per.items():
        giorni = {g for g, _t, _e in righe}
        ultimo = max(giorni)
        valore = None
        if len(righe) >= MIN_TENTATIVI and len(giorni) >= MIN_GIORNI:
            num = den = 0.0
            for g, tipo, esito in righe:
                w = TIPI[tipo] * 0.5 ** (max(0, (oggi - g).days) / MEZZA_VITA_GIORNI)
                num += w * ESITI[esito]
                den += w
            v = 100.0 * num / den if den else 0.0
            v *= 0.5 ** (max(0, (oggi - ultimo).days) / CALO_GIORNI)
            valore = int(round(min(100.0, max(0.0, v))))
        out[aid] = {"valore": valore, "parola": parola(valore), "tentativi": len(righe),
                    "giorni": len(giorni), "ultimo": ultimo.isoformat()}
    return out


def livello(argomenti_piano: list[int], pad: dict) -> int | None:
    """La misura del giorno della verifica: la media delle padronanze degli argomenti del piano
    misurati, solo se almeno `MISURATI_PER_LIVELLO` di loro lo sono; altrimenti None."""
    if not argomenti_piano:
        return None
    vals = [pad[a]["valore"] for a in argomenti_piano
            if a in pad and pad[a]["valore"] is not None]
    if len(vals) < MISURATI_PER_LIVELLO * len(argomenti_piano):
        return None
    return int(round(sum(vals) / len(vals)))


def lacune(argomenti_piano: list[dict], pad: dict, obiettivo: int, giorni_piano: list[dict],
           oggi) -> list[dict]:
    """Gli argomenti del piano misurati e sotto `obiettivo`, dal più debole, ognuno con la lezione
    successiva: il prossimo giorno del piano (da oggi, non fatto) che ha una sua pagina, oppure il
    prossimo ripasso. `argomenti_piano`: dict con `id`, `numero` (la posizione nell'elenco della
    verifica, quella che si dice a voce) e `pagine` (id)."""
    oggi = _d(oggi).isoformat()
    avanti = [g for g in giorni_piano if g["giorno"] >= oggi and not g.get("fatto")]
    out = []
    for a in argomenti_piano:
        p = pad.get(a["id"])
        if not p or p["valore"] is None or p["valore"] >= obiettivo:
            continue
        sue = set(a.get("pagine") or ())
        dopo = next((g for g in avanti if g.get("fase") == "studio" and sue & set(g["pagine"])),
                    None) or next((g for g in avanti if g.get("fase") == "ripasso"
                                   and sue & set(g["pagine"])), None)
        out.append({"argomento": a["id"], "numero": a.get("numero"), "valore": p["valore"],
                    "parola": p["parola"],
                    "lezione": ({"giorno": dopo["giorno"], "fase": dopo["fase"],
                                 "attivita": dopo.get("attivita")} if dopo else None)})
    out.sort(key=lambda x: (x["valore"], x["numero"] or 0))
    return out
