import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""
Il cassetto dei file col modello vero (17/10/2026, issue #58; docs/aree/immagini-allegati.md):
Brain con Ollama (quello di Config, o `--url`/`--modello`/`--num-ctx` per il 26B della DGX), un
cassetto vero in una cartella temporanea riempito con file finti datati (nomi e contenuti di
fantasia), chi parla riconosciuto dalla voce. Se il modello non sceglie il tool giusto, la
funzione c'è ma a voce non si usa.

Casi, ognuno in una conversazione nuova:

- **ritrova** → `allegato_leggi(cassetto=…)` che porta al file giusto: «il file di ieri», «la
  bolletta di <giorno di 4 giorni fa>», «le foto di questa settimana»;
- **dopo la revisione** (la frase della revisione nella storia, come la dice il ciclo) →
  `cassetto_gestisci`: «tienili tutti» (tieni, tutti nell'archivio), «elimina quello dello
  scontrino» (elimina, solo quello), «tienili ancora una settimana» (ancora, tutti prorogati);
- **contrari**: un file arrivato in questo turno (nessun `cassetto`, la risposta dal file);
  «archivia questa bolletta» col file adesso (il file nell'archivio, con `allegato_archivia` o
  `immagine_archivia` che lo passa al file; niente cassetto); i file di
  un'altra persona adulta, per nome e come «mia moglie» (rifiutati dal tool: nessun file
  letto, niente inventato).

Le percentuali per gruppo alla fine (criterio della #58: ritrova e revisione ≥ 90 %, contrari
100 %). Uso:

    python prove/prova_cassetto_ollama.py [giri]
    CALLIOPE_LLM_PROFILO=gemma4-26b-ollama python prove/prova_cassetto_ollama.py 3 --url http://127.0.0.1:11440 --modello gemma4:26b-a4b-it-qat --num-ctx 36864

Col 26B solo a DGX libera e col `num_ctx` del modello già caricato (un altro lo ricarica).
"""

import argparse
import dataclasses
import datetime
import json
import shutil
import tempfile
import time
from pathlib import Path

import allegati_finti as A
from prove import immagini_finte as F
from calliope.allegati import prepara
from calliope.brain import Brain
from calliope.cassetto import GIORNO_S, GIORNI_SETTIMANA, Cassetto
from calliope.config import Config
from calliope.immagini import Album, Immagine
from calliope.immagini import prepara as prepara_foto
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext

ERRORI = []
TEMPI = []
GRUPPI: dict[str, list[bool]] = {"ritrova": [], "revisione": [], "contrari": []}
CARTELLE: list[Path] = []
ARGS = argparse.Namespace(url="", modello="", num_ctx=0)

PREVENTIVO = ("Preventivo dell'idraulico Bruno Ferretti\nSostituzione del miscelatore della "
              "cucina e del sifone.\nTotale 340 euro, IVA compresa. Valido 30 giorni.")
SCONTRINO = ("Farmacia del Corso\nScontrino fiscale\nSciroppo per la tosse 8,90\n"
             "Cerotti 3,20\nTotale 12,10 euro")
SEGRETO_ALTRA = "codice cliente QX-4471"


def verifica(gruppo, nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  {dettaglio}" if dettaglio else ""), flush=True)
    GRUPPI[gruppo].append(bool(ok))
    if not ok:
        ERRORI.append(nome)


class Prof:
    def __init__(self, pid, nome, admin=False):
        self.id, self.name, self.admin = pid, nome, admin
        self.nascita, self.tutori = None, []
        self.gender, self.preferred_voice, self.giovane, self.tono = "m", None, False, None


PERSONE = {"Dario": Prof("dario", "Dario", admin=True), "Teodora": Prof("teodora", "Teodora")}


class Speakers:
    users = dict(PERSONE)

    def get(self, n):
        return PERSONE.get(n)

    def by_id(self, i):
        return next((p for p in PERSONE.values() if p.id == i), None)

    def known_speakers(self):
        return list(PERSONE)


class SC:
    """Dario riconosciuto dalla voce in questa frase (il cassetto lo chiede)."""
    current_speaker = "Dario"
    current_level = "familiare"
    identified_by = "voce"
    from_session = False
    sfida = None
    sfida_superata = False


class Archivio:
    def __init__(self):
        self.cartella = Path(tempfile.mkdtemp(prefix="calliope-cassetto-arch-"))
        CARTELLE.append(self.cartella)

    def sveglia(self):
        pass


def cfg_nuova() -> Config:
    cfg = Config()
    cfg.storia_inattiva_s = 0
    if ARGS.url:
        cfg.llm_native_url = ARGS.url
    if ARGS.modello:
        cfg.llm_model = ARGS.modello
    if ARGS.num_ctx:
        cfg.llm_num_ctx = ARGS.num_ctx
    return cfg


def cassetto_nuovo() -> Cassetto:
    tmp = Path(tempfile.mkdtemp(prefix="calliope-cassetto-ollama-"))
    CARTELLE.append(tmp)
    c = Cassetto(str(tmp / "memoria.db"), None, log=lambda *a: None)
    c.registry = Speakers()
    c.archivio = Archivio()
    c.registro = lambda *a: None
    return c


def metti(cas, giorni_fa: float, persona, dati, nome, categoria, **kw) -> int:
    """Un file arrivato `giorni_fa` giorni fa (l'orologio del cassetto spostato per l'entrata)."""
    t = time.time() - giorni_fa * GIORNO_S
    cas.ora = lambda: t
    try:
        return cas.metti(persona, dati, nome, categoria, fonte="telefono", **kw)
    finally:
        cas.ora = time.time


def foto_scontrino() -> Immagine:
    jpeg, w, h = prepara_foto(F.jpeg(F.scontrino()), 1280)
    return Immagine(jpeg, w, h, fonte="telefono", persona="dario")


def nuovo(cas):
    cfg = cfg_nuova()
    reg = build_registry(casa=True, allegati=True, archivio=True, cassetto=True,
                         immagini={"storia": "messaggio", "pc": False, "archivio": True})
    chiamate = []

    # Si conta la funzione del tool (dopo la politica di ToolRegistry.call), con l'esito
    def contata(nome, f):
        def g(ctx, **a):
            r = f(ctx, **a)
            chiamate.append((nome, a, r))
            return r
        return g
    for nome, spec in list(reg._tools.items()):
        reg.register(dataclasses.replace(spec, func=contata(nome, spec.func)))
    ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SC(), speaker=None)
    ctx.cassetto = cas
    ctx.archivio = Archivio()
    ctx.immagini = Album(6)
    b = Brain(cfg, reg, ctx)
    b.tool_ctx.cassetto = cas
    return b, chiamate


def turno(b, testo, allegati=None, immagini=None):
    t0 = time.perf_counter()
    first, out = None, ""
    for att in allegati or ():          # la porta unica dei dati non fidati, come il ciclo
        b.allega_non_fidato(att.fonte_dato, att, att.nome)
    for piece in b.stream_reply(testo, "familiare", immagini=immagini):
        if first is None and piece.strip():
            first = time.perf_counter() - t0
        out += piece
    TEMPI.append(first or time.perf_counter() - t0)
    return " ".join(out.split())


def _ok(r) -> bool:
    if isinstance(r, str):
        try:
            r = json.loads(r)
        except ValueError:
            return False
    return isinstance(r, dict) and r.get("ok", True) is not False and "errore" not in r


def letture_cassetto(chiamate):
    """Le chiamate di allegato_leggi sulla strada del cassetto (cassetto, o il solo nome)."""
    return [(a, r) for n, a, r in chiamate if n == "allegato_leggi"
            and (a.get("cassetto") or ((a.get("minore") or a.get("ragazzo") or a.get("di"))
                                       and a.get("allegato") in (None, "")))]


def ids_esito(r) -> set:
    """Gli id del cassetto nell'esito di allegato_leggi: il file letto o l'elenco trovato."""
    if not isinstance(r, dict):
        return set()
    voci = [r.get("file")] + [t.get("id") for t in r.get("trovati") or []]
    return {int(str(v)[1:]) for v in voci if str(v or "").startswith("C")
            and str(v)[1:].isdigit()}


def gestioni(chiamate):
    return [(a, r) for n, a, r in chiamate if n == "cassetto_gestisci"]


def breve(chiamate):
    return [(n, {k: v for k, v in a.items()}) for n, a, _ in chiamate]


# ─────────────────────────── ritrova ───────────────────────────
GIORNO_BOLLETTA = 4


def cassetto_ritrova():
    cas = cassetto_nuovo()
    ids = {
        "preventivo": metti(cas, 1, "dario", A.pdf([PREVENTIVO]), "preventivo bagno.pdf", "pdf"),
        "bolletta": metti(cas, GIORNO_BOLLETTA, "dario", A.pdf([A.BOLLETTA]),
                          "bolletta luce.pdf", "pdf"),
        "excel": metti(cas, 5, "dario", A.xlsx({"Spese": [["Voce", "Euro"], ["Affitto", 700]]}),
                       "spese ottobre.xlsx", "excel"),
    }
    f = foto_scontrino()
    ids["foto1"] = metti(cas, 2, "dario", f.jpeg, "Foto 1.jpg", "immagine",
                         larghezza=f.larghezza, altezza=f.altezza)
    ids["foto2"] = metti(cas, 3, "dario", f.jpeg, "Foto 2.jpg", "immagine",
                         larghezza=f.larghezza, altezza=f.altezza)
    return cas, ids


def caso_ritrova():
    giorno = GIORNI_SETTIMANA[(datetime.date.today()
                               - datetime.timedelta(days=GIORNO_BOLLETTA)).weekday()]
    casi = [("Ritrovami il file che ti ho mandato ieri.", {"preventivo"}, True),
            (f"Cosa diceva la bolletta che ti ho mandato {giorno}?", {"bolletta"}, True),
            ("Fammi vedere le foto che ti ho mandato questa settimana.", {"foto1", "foto2"},
             False)]
    for domanda, attesi, unico in casi:
        cas, ids = cassetto_ritrova()
        b, ch = nuovo(cas)
        r = turno(b, domanda)
        bersagli = {ids[k] for k in attesi}
        # Riuscita: un esito del tool (non le sue parole) che porta al file giusto: il file
        # letto, o l'elenco che lo contiene se sono più d'uno (le foto)
        giuste = [a for a, ris in letture_cassetto(ch)
                  if _ok(ris) and (ids_esito(ris) <= bersagli if unico else True)
                  and ids_esito(ris) & bersagli]
        verifica("ritrova", f"«{domanda}» → allegato_leggi(cassetto=…) sul file giusto",
                 bool(giuste) and not gestioni(ch)
                 and not any(n == "allegato_leggi" and (a, x) not in letture_cassetto(ch)
                             for n, a, x in ch),
                 f"{breve(ch)} · {r[:160]}")
        cas.close()


# ─────────────────────────── dopo la revisione ───────────────────────────
def cassetto_revisione():
    cas = cassetto_nuovo()
    ids = {"scontrino": metti(cas, 6.05, "dario", A.pdf([SCONTRINO]), "scontrino farmacia.pdf",
                              "pdf"),
           "bolletta": metti(cas, 6.05, "dario", A.pdf([A.BOLLETTA]), "bolletta gas.pdf", "pdf")}
    f = foto_scontrino()
    ids["foto"] = metti(cas, 6.05, "dario", f.jpeg, "Foto 3.jpg", "immagine",
                        larghezza=f.larghezza, altezza=f.altezza)
    return cas, ids


def caso_revisione():
    casi = [("Tienili tutti.", "tieni"), ("Elimina quello dello scontrino.", "elimina"),
            ("Tienili ancora una settimana.", "ancora")]
    for domanda, azione in casi:
        cas, ids = cassetto_revisione()
        b, ch = nuovo(cas)
        turno(b, "Buongiorno Calliope.")
        info = cas.da_dire("dario")
        frase = cas.frase(info, schermo=False)
        cas.segna_detto("dario", revisione=info["revisione"])
        b.record_announcement(frase, fonte=None)
        n0 = len(ch)
        r = turno(b, domanda)
        dopo = ch[n0:]
        g = [a for a, ris in gestioni(dopo) if str(a.get("azione")) == azione and _ok(ris)]
        attivi = {x["id"] for x in cas.elenco("dario")}
        if azione == "tieni":
            effetto = not attivi and len(list(cas.archivio.cartella.rglob("*.*"))) == 3
        elif azione == "elimina":
            effetto = attivi == {ids["bolletta"], ids["foto"]}
        else:
            effetto = (len(attivi) == 3 and all(x["scade"] > time.time() + 6 * GIORNO_S
                                                for x in cas.elenco("dario")))
        verifica("revisione", f"revisione («{frase[:40]}…»), «{domanda}» → "
                 f"cassetto_gestisci({azione}) e l'effetto",
                 bool(g) and effetto, f"{breve(dopo)} · attivi {len(attivi)} · {r[:160]}")
        cas.close()


# ─────────────────────────── contrari ───────────────────────────
def caso_contrari():
    # Un file arrivato adesso: è nella conversazione (e anche nel cassetto, come nel ciclo)
    cas, _ = cassetto_ritrova()
    b, ch = nuovo(cas)
    att = prepara(A.pdf([A.BOLLETTA]), "bolletta settembre.pdf", Config(), persona="dario")
    cas.metti_allegato(att, "dario")
    r = turno(b, "Quanto devo pagare in questa bolletta?", [att])
    verifica("contrari", "file arrivato adesso: nessun cassetto, la risposta dal file",
             not letture_cassetto(ch) and not gestioni(ch) and "82" in r,
             f"{breve(ch)} · {r[:160]}")
    cas.close()
    # «Archivia questa bolletta» col file adesso: l'archivio, non il cassetto
    cas, _ = cassetto_ritrova()
    b, ch = nuovo(cas)
    att = prepara(A.pdf([A.BOLLETTA]), "bolletta settembre.pdf", Config(), persona="dario")
    cas.metti_allegato(att, "dario")
    r = turno(b, "Archivia questa bolletta.", [att])
    archiviati = list(Path(b.tool_ctx.archivio.cartella).rglob("*.pdf"))
    verifica("contrari", "«archivia questa bolletta» col file adesso: nell'archivio, niente "
             "cassetto", len(archiviati) == 1 and not gestioni(ch) and not letture_cassetto(ch),
             f"{breve(ch)} · {r[:160]}")
    cas.close()
    # I file di un'altra persona adulta, per nome o con la parentela (revisione della PR #143:
    # «mia moglie» dava il file di chi parla): il tool li rifiuta, niente letto né inventato
    for frase in ("Leggimi il file che Teodora ti ha mandato ieri.",
                  "Leggimi il file che mia moglie ti ha mandato ieri."):
        cas, _ = cassetto_ritrova()
        metti(cas, 1, "teodora", A.pdf([f"Abbonamento palestra, {SEGRETO_ALTRA}."]),
              "palestra.pdf", "pdf")
        b, ch = nuovo(cas)
        r = turno(b, frase)
        # Il tool può rileggere il cassetto di chi parla (è suo); non deve uscire niente del
        # file di un altro, né il file di chi parla presentato come quello dell'altra persona
        letti = [(a, x) for a, x in letture_cassetto(ch)
                 if _ok(x) and "teodora" in json.dumps(x, ensure_ascii=False).lower()]
        detto = r.lower()
        verifica("contrari", f"«{frase}»: nessun file dell'altra letto né inventato",
                 not letti and "qx" not in detto and "4471" not in detto
                 and not any(p in detto for p in ("340", "preventivo", "ferretti",
                                                  "idraulico", "miscelatore")),
                 f"{breve(ch)} · {r[:160]}")
        cas.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("giri", nargs="?", type=int, default=1)
    ap.add_argument("--url", default="")
    ap.add_argument("--modello", default="")
    ap.add_argument("--num-ctx", type=int, default=0,
                    help="il num_ctx del modello già caricato (un altro lo fa ricaricare)")
    ap.add_argument("--casi", default="ritrova,revisione,contrari",
                    help="i gruppi da provare (ritrova, revisione, contrari)")
    ARGS = ap.parse_args()
    gruppi = set(ARGS.casi.split(","))
    cas0 = cassetto_nuovo()
    b, _ = nuovo(cas0)
    print(f"modello: {b.cfg.llm_model} ({b.cfg.llm_native_url})", flush=True)
    b.warmup()
    cas0.close()
    try:
        for g in range(ARGS.giri):
            print(f"\n— giro {g + 1} —", flush=True)
            for nome, f in (("ritrova", caso_ritrova), ("revisione", caso_revisione),
                            ("contrari", caso_contrari)):
                if nome in gruppi:
                    f()
    finally:
        for c in CARTELLE:
            shutil.rmtree(c, ignore_errors=True)
    TEMPI.sort()
    print(f"\nprima frase: mediana {TEMPI[len(TEMPI) // 2]:.2f} s, massimo {TEMPI[-1]:.2f} s "
          f"({len(TEMPI)} turni)")
    for k, v in GRUPPI.items():
        print(f"{k}: {sum(v)}/{len(v)} ({100 * sum(v) / max(1, len(v)):.0f} %)")
    ok = (all(sum(v) >= 0.9 * len(v) for k, v in GRUPPI.items() if k != "contrari" and v)
          and all(GRUPPI["contrari"]))
    print(f"\n{'Tutto bene' if not ERRORI else f'{len(ERRORI)} non riuscite: ' + ', '.join(ERRORI)}"
          f" — criterio della #58 {'raggiunto' if ok else 'NON raggiunto'}")
    sys.exit(0 if ok else 1)
