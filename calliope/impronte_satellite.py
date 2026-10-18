"""
Impronte della voce per satellite (15/10/2026, proposta di Dario; docs/aree/stt-tts.md, «Impronte
della voce per satellite»).

Il caso vero (15/10 mattina, telefono in auto): chi amministra preso a 0,444 e 0,399 (soglia
0,48), il minore secondo a 0,358/0,354 → ospite; negli stessi minuti sei frasi sue tra 0,60 e
0,76 sullo stesso telefono. Il canale sposta l'impronta, e quella di chi amministra non si
adattava più (coseno 0,900 con l'arruolamento = `speaker_adapt_max_drift`, 07/10).

Per ogni persona (famiglia, minori compresi, e conoscenti: decisione 0030) un'impronta in più per
**satellite** (`sat:<nome>`) e una per **tipo di canale** (`canale:telefono`, `canale:satellite`,
`canale:locale`), il ripiego per un satellite nuovo. L'impronta di partenza (arruolamento e
adattamento di sempre) resta. Il punteggio di una persona per una frase è il **massimo** fra
quella di partenza e quella del satellite da cui arriva (o del suo canale, se il satellite non ne
ha ancora una); la soglia non cambia.

- **Solo frasi sicure** (`sicura`): decisa dalla voce, sopra `speaker_adapt_threshold`, margine sul
  secondo profilo almeno `speaker_impronte_margine`, voce di almeno
  `speaker_impronte_min_voce_s`; mai zona grigia, frase breve, continuità, compagnia, voce incerta
  o minore vicino.
- **Seme** dopo `speaker_impronte_seme_frasi` frasi sicure (la loro media, mai la prima da sola);
  le frasi in attesa del seme stanno solo in memoria.
- **Deriva limitata** due volte: coseno almeno `speaker_impronte_deriva_arruolamento` con
  l'impronta d'arruolamento e almeno `speaker_impronte_deriva_seme` con il proprio seme.
- **Per tutti allo stesso modo**: con un'impronta del telefono solo per chi amministra il verso
  pericoloso (il minore preso per lui) peggiorerebbe. Le regole di protezione
  (`minori.piu_protetto`, `minori_margine_amministra`, la sfida) restano, sui punteggi nuovi.

Interruttore `speaker_impronte_satellite`: «spento» (di serie), «ombra» (si imparano e si salvano;
nel registro dei turni, `voce.impronte_satellite`, la decisione con e senza; decide quella di
oggi), «attivo». Sono dati biometrici: stanno con le impronte di sempre (speakers.json per la
famiglia, il file dei conoscenti per loro), con la stessa tenuta e cancellazione.

`riassunto`/`testo`: la sezione di `calliope stato --turni` (solo numeri, per satellite).
"""
from __future__ import annotations

import dataclasses
import datetime

import numpy as np

SPENTO, OMBRA, ATTIVO = "spento", "ombra", "attivo"


def modo(cfg) -> str:
    """`speaker_impronte_satellite`: «spento», «ombra» o «attivo» (False/True dal YAML valgono
    spento/attivo; un valore sconosciuto vale spento: nel dubbio come oggi)."""
    v = getattr(cfg, "speaker_impronte_satellite", SPENTO)
    if v is False or v is None:
        return SPENTO
    if v is True:
        return ATTIVO
    v = str(v).strip().lower()
    return v if v in (SPENTO, OMBRA, ATTIVO) else SPENTO


def chiavi(satellite: str | None, canale: str | None) -> tuple[str, ...]:
    """Le chiavi delle impronte di una frase, dalla più precisa: il satellite per nome, poi il
    tipo di canale (il ripiego per un satellite nuovo). L'audio di questo computer è
    («sat:locale», «canale:locale»)."""
    out = []
    nome = " ".join(str(satellite or "").split())
    if nome:
        out.append(f"sat:{nome}")
    out.append(f"canale:{str(canale or 'satellite').strip().lower() or 'satellite'}")
    return tuple(out)


def _unit(v) -> np.ndarray | None:
    if v is None:
        return None
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    n = float(np.linalg.norm(v))
    return (v / n).astype(np.float32) if n > 1e-9 else None


@dataclasses.dataclass
class Impronta:
    """L'impronta di una persona su un satellite (o un canale). `attesa`: le frasi sicure prima
    del seme, solo in memoria (mai su disco)."""
    v: np.ndarray | None = None
    seme: np.ndarray | None = None
    n: int = 0                       # frasi sicure contate
    il: str = ""                     # AAAA-MM-GG dell'ultimo aggiornamento
    attesa: list = dataclasses.field(default_factory=list)

    @property
    def pronta(self) -> bool:
        return self.v is not None

    def a_dict(self) -> dict:
        return {"v": [round(float(x), 6) for x in self.v],
                "seme": [round(float(x), 6) for x in (self.seme if self.seme is not None
                                                      else self.v)],
                "n": int(self.n), "il": self.il}

    @classmethod
    def da_dict(cls, d) -> "Impronta | None":
        if not isinstance(d, dict):
            return None
        v = _unit(d.get("v")) if d.get("v") else None
        if v is None:
            return None
        seme = _unit(d.get("seme")) if d.get("seme") else None
        if seme is not None and seme.shape != v.shape:
            seme = None
        n = d.get("n")
        return cls(v=v, seme=seme if seme is not None else v.copy(),
                   n=int(n) if isinstance(n, (int, float)) else 0,
                   il=str(d.get("il") or ""))


def leggi(d) -> dict[str, Impronta]:
    """Le impronte per satellite da un profilo letto dal disco (un campo assente o rovinato:
    nessuna)."""
    out: dict[str, Impronta] = {}
    if not isinstance(d, dict):
        return out
    for k, x in d.items():
        try:
            imp = Impronta.da_dict(x)
        except (TypeError, ValueError):      # un campo rovinato: quella no, le altre sì
            imp = None
        if imp is not None and isinstance(k, str) and k:
            out[k] = imp
    return out


def scrivi(impronte: dict | None) -> dict:
    """Solo le impronte nate (con il seme): le frasi in attesa non vanno su disco."""
    return {k: imp.a_dict() for k, imp in (impronte or {}).items() if imp.pronta}


def migliore(emb, impronte: dict | None, ch) -> tuple[float | None, str | None]:
    """(punteggio, chiave) con l'impronta del satellite, o del canale se il satellite non ne ha
    ancora una; (None, None) senza nessuna delle due."""
    if emb is None or not impronte or not ch:
        return None, None
    for k in ch:
        imp = impronte.get(k)
        if imp is not None and imp.pronta and imp.v.shape == np.shape(emb):
            return float(np.dot(emb, imp.v)), k
    return None, None


def punteggio(emb, base, impronte: dict | None, ch) -> tuple[float, str]:
    """(punteggio, fonte) di una persona per questa frase: il massimo fra l'impronta di partenza
    e quella del satellite (o del canale). Fonte «base», «sat:…» o «canale:…»."""
    s = float(np.dot(emb, base)) if base is not None else -1.0
    ss, k = migliore(emb, impronte, ch)
    if ss is not None and ss > s:
        return ss, k
    return s, "base"


def sicura(cfg, come: str | None, sim: float | None, sim2: float | None, voce_s: float, *,
           compagnia: bool = False, incerta: bool = False, minore_vicino: bool = False,
           continuita: bool = False) -> bool:
    """La frase può insegnare l'impronta del satellite? Solo una voce decisa dalla voce, netta e
    lunga abbastanza, senza dubbi intorno."""
    if come != "voce" or sim is None or compagnia or incerta or minore_vicino or continuita:
        return False
    if float(voce_s or 0.0) < float(getattr(cfg, "speaker_impronte_min_voce_s", 1.5)):
        return False
    if sim < float(getattr(cfg, "speaker_adapt_threshold", 0.58)):
        return False
    m = float(getattr(cfg, "speaker_impronte_margine", 0.15))
    return sim2 is None or sim - float(sim2) >= m


def impara(impronte: dict, emb, ch, iniziale, cfg, oggi: str | None = None) -> list[str]:
    """Una frase sicura entra nelle impronte del satellite e del canale (`ch`). Restituisce le
    chiavi cambiate (nate o aggiornate). `iniziale`: l'impronta dell'arruolamento (per i
    conoscenti quella salvata), il limite della deriva."""
    emb = _unit(emb)
    if emb is None or not ch:
        return []
    ini = _unit(iniziale)
    oggi = oggi or datetime.date.today().isoformat()
    semi = max(1, int(getattr(cfg, "speaker_impronte_seme_frasi", 3) or 3))
    alpha = float(getattr(cfg, "speaker_impronte_alpha", 0.1))
    d_ini = float(getattr(cfg, "speaker_impronte_deriva_arruolamento", 0.70))
    d_seme = float(getattr(cfg, "speaker_impronte_deriva_seme", 0.85))
    massimo = max(2, int(getattr(cfg, "speaker_impronte_max", 12) or 12))
    cambiate = []
    for k in ch:
        imp = impronte.get(k)
        if imp is None:
            if len(impronte) >= massimo:
                # Il satellite più vecchio esce (quelle in attesa per prime)
                vecchia = min(impronte, key=lambda x: (impronte[x].pronta, impronte[x].il,
                                                       impronte[x].n))
                impronte.pop(vecchia, None)
            imp = impronte[k] = Impronta()
        if ini is not None and ini.shape != emb.shape:
            continue
        if not imp.pronta:
            imp.attesa.append(emb)
            del imp.attesa[:-semi]
            if len(imp.attesa) < semi:
                continue
            seme = _unit(np.mean(np.stack(imp.attesa), axis=0))
            if seme is None or (ini is not None and float(np.dot(seme, ini)) < d_ini):
                # Troppo lontano dall'arruolamento: si aspetta la frase dopo (scorre)
                imp.attesa.pop(0)
                continue
            imp.v, imp.seme, imp.n, imp.il, imp.attesa = seme, seme.copy(), semi, oggi, []
            cambiate.append(k)
            continue
        nuova = _unit((1 - alpha) * imp.v + alpha * emb)
        if nuova is None:
            continue
        if ini is not None and float(np.dot(nuova, ini)) < d_ini:
            continue
        if imp.seme is not None and float(np.dot(nuova, imp.seme)) < d_seme:
            continue
        imp.v, imp.n, imp.il = nuova, imp.n + 1, oggi
        cambiate.append(k)
    return cambiate


# ─────────────────────────── il registro dei turni ───────────────────────────

def _luogo(rec: dict) -> str:
    a = rec.get("ascolto") if isinstance(rec.get("ascolto"), dict) else {}
    return str(a.get("satellite") or a.get("canale") or "locale")


def _chi(d: dict) -> str | None:
    """Chi vale in una decisione del blocco: la persona di casa o il conoscente."""
    if d.get("nome"):
        return str(d["nome"])
    return f"conoscente:{d['conoscente']}" if d.get("conoscente") else None


def base_sicura(senza: dict) -> bool:
    """La decisione senza le impronte del satellite è sicura: decisa dalla voce (sopra la soglia,
    con il margine sul secondo profilo). Zona grigia, frase breve, continuità, il profilo più
    protetto, il satellite di chi è stato riconosciuto da poco sono una base incerta: uno
    scambio contro di lei è più spesso una correzione che un errore (18/10, issue #159: l'unico
    «minore → chi amministra» del 16/10 era deciso per continuità)."""
    return senza.get("come") == "voce"


def riassunto(turni: list[dict]) -> dict:
    """Per satellite, dai blocchi `voce.impronte_satellite` (ombra o attivo): frasi con il blocco,
    rifiutate dalla decisione senza le impronte e riconosciute con («recuperate»), il contrario
    («perse»), scambi fra persone (e quelli fra un minore e chi amministra, nei due versi),
    divisi fra «base sicura» e «base incerta» (`base_sicura`, dal 18/10), frasi passate dalla
    zona grigia alla voce, frasi che hanno insegnato un'impronta."""
    per: dict = {}
    for r in turni:
        v = r.get("voce") if isinstance(r.get("voce"), dict) else None
        b = v.get("impronte_satellite") if v else None
        if not isinstance(b, dict):
            continue
        con = b.get("con") if isinstance(b.get("con"), dict) else {}
        senza = b.get("senza") if isinstance(b.get("senza"), dict) else {}
        d = per.setdefault(_luogo(r), {"frasi": 0, "recuperate": 0, "perse": 0, "scambi": 0,
                                       "minore_ad_amministra": 0, "amministra_a_minore": 0,
                                       "scambi_incerti": 0, "minore_ad_amministra_incerti": 0,
                                       "amministra_a_minore_incerti": 0,
                                       "piu_voce": 0, "imparate": 0, "dal_satellite": 0,
                                       "modo": b.get("modo")})
        d["frasi"] += 1
        d["modo"] = b.get("modo") or d["modo"]
        nc, ns = _chi(con), _chi(senza)
        if ns is None and nc is not None:
            d["recuperate"] += 1
        elif ns is not None and nc is None:
            d["perse"] += 1
        elif ns is not None and nc is not None and ns != nc:
            # Con la base sicura «scambi», con quella incerta «scambi_incerti» (18/10, #159)
            suf = "" if base_sicura(senza) else "_incerti"
            d["scambi" + suf] += 1
            if senza.get("minore") and con.get("amministra"):
                d["minore_ad_amministra" + suf] += 1
            if senza.get("amministra") and con.get("minore"):
                d["amministra_a_minore" + suf] += 1
        if con.get("come") == "voce" and senza.get("come") != "voce" and nc == ns:
            d["piu_voce"] += 1
        if b.get("imparata"):
            d["imparate"] += 1
        if str(con.get("fonte") or "base") != "base":
            d["dal_satellite"] += 1
    return {"satelliti": per}


def testo(r: dict) -> str:
    per = (r or {}).get("satelliti") or {}
    if not per:
        return ("Impronte per satellite: nessun turno con la misura "
                "(speaker_impronte_satellite spento).")
    righe = ["Impronte per satellite (con le impronte del satellite rispetto a senza):"]
    for luogo in sorted(per):
        d = per[luogo]
        righe.append(
            f"  {luogo} ({d.get('modo') or '?'}): {d['frasi']} frasi, rifiutate → riconosciute "
            f"{d['recuperate']}, riconosciute → rifiutate {d['perse']}, scambi fra persone "
            f"con la base sicura {d['scambi']} (minore → chi amministra "
            f"{d['minore_ad_amministra']}, chi amministra → minore {d['amministra_a_minore']}), "
            f"con la base incerta {d.get('scambi_incerti', 0)} (minore → chi amministra "
            f"{d.get('minore_ad_amministra_incerti', 0)}, chi amministra → minore "
            f"{d.get('amministra_a_minore_incerti', 0)}), zona grigia → voce {d['piu_voce']}; "
            f"punteggio "
            f"dall'impronta del satellite {d['dal_satellite']}, frasi che l'hanno insegnata "
            f"{d['imparate']}")
    return "\n".join(righe)


# ─────────────────────────── cancellazione da terminale ───────────────────────────

def svuota_file(path, persona_id: str | None = None) -> int:
    """Via le impronte per satellite da un file di profili (speakers.json: un elenco; il file dei
    conoscenti: {"conoscenti": [...]}) e dalla sua copia `.bak`, di una persona (per id) o di
    tutti: per `calliope conserva --svuota` da un altro processo. Quante ne ha tolte (nel file)."""
    import json
    from pathlib import Path

    from .persistenza import scrivi_json
    tolte = 0
    p = Path(path)
    for f in (p, p.with_name(p.name + ".bak")):
        if not f.exists():
            continue
        try:
            dati = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        profili = dati.get("conoscenti") if isinstance(dati, dict) else dati
        n = 0
        for d in profili or ():
            if not isinstance(d, dict) or not d.get("impronte_satellite"):
                continue
            if persona_id is not None and str(d.get("id")) != str(persona_id):
                continue
            n += len(d["impronte_satellite"]) if isinstance(d["impronte_satellite"], dict) else 1
            d.pop("impronte_satellite", None)
        if n:
            scrivi_json(f, dati, copia=False)
        if f == p:
            tolte = n
    return tolte
