import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Il meteo di casa con il modello vero della voce (Ollama locale, `llm_model`), l'HA finto e
una ricerca web finta (09/10, decisione di Dario: «il meteo senza indicazioni è quello di
casa»; nomi di fantasia, la casa è a Borgoverde).

1. Entità meteo esposta in HA: «Che tempo fa?» e «Domani piove?» → meteo_leggi (domani con
   quando=domani). Contrari: «Che tempo fa a Parigi?» (mai meteo_leggi), «Che tempo fa da
   Ettore?» (mai meteo_leggi), «Che temperatura c'è in sala?» (casa_stato, mai meteo_leggi).
2. Nessuna entità esposta, città in configurazione: «Che tempo fa?» → web_cerca con Borgoverde.
3. Né entità né città: «Che tempo fa?» → nessuna ricerca, chiede dove; «A Borgoverde.» →
   web_cerca con Borgoverde e, per chi amministra, la proposta di ricordarla; «Sì.» →
   citta_casa_salva salvata. Per una familiare: mai salvata.

Fallisce se un caso atteso riesce meno di 2 volte su 3 (con 3 giri) o se un contrario sbaglia
anche una volta. Alla fine `ollama stop` non lo fa: lo fa chi lancia.

    python prove\\prova_meteo_casa_ollama.py      # 3 giri
    python prove\\prova_meteo_casa_ollama.py 1    # 1 giro
"""

import json
import tempfile
import time
from pathlib import Path

from prove.ha_finto import TOKEN, FakeHA, _e, entita_casa
from calliope import luogo
from calliope.brain import Brain
from calliope.casa import load_casa
from calliope.config import Config
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext, ToolSpec
from calliope.tools.web import web_spec

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
CITTA = "Borgoverde"
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


class Prof:
    def __init__(self, pid, name, admin=False):
        self.id, self.name, self.admin = pid, name, admin


class Speakers:
    def __init__(self):
        self.p = {"Dario": Prof("dario-id", "Dario", True), "Bianca": Prof("bianca-id", "Bianca")}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self, name, level):
        self.current_speaker, self.current_level, self.from_session = name, level, False
        self.identified_by, self.profile_level = "voce", level
        self.sfida, self.sfida_superata, self.conferma_breve = None, False, False


METEO = _e("weather.forecast_casa", "Forecast Casa", None, "partlycloudy",
           attr={"temperature": 17.4, "humidity": 71, "wind_speed": 12.6,
                 "temperature_unit": "°C", "wind_speed_unit": "km/h", "supported_features": 3})


def previsioni(ha):
    import datetime as dt
    oggi = dt.date.today()

    def iso(g, h):
        return dt.datetime(g.year, g.month, g.day, h).astimezone().astimezone(
            dt.timezone.utc).isoformat()
    ha.previsioni[("weather.forecast_casa", "daily")] = [
        {"datetime": iso(oggi + dt.timedelta(days=i), 12),
         "condition": ["partlycloudy", "rainy", "sunny"][i % 3], "temperature": 18 - i,
         "templow": 11, "precipitation_probability": [10, 85, 0][i % 3]} for i in range(5)]


def ambiente(tmp: Path, meteo: bool, citta: str, chiamate: list):
    tmp.mkdir(parents=True, exist_ok=True)
    ha = FakeHA(entita=entita_casa() + ([METEO] if meteo else [])).avvia()
    previsioni(ha)
    (tmp / "segreti.yaml").write_text(f'home_assistant:\n  token: "{TOKEN}"\n', encoding="utf-8")
    cfg = Config()
    cfg.config_dir, cfg.casa_url, cfg.casa_timeout_s = str(tmp), ha.url, 2.0
    cfg.casa_citta = citta
    casa, _ = load_casa(cfg, log=lambda m: None)
    casa.diagnosi(riprova=True)
    casa.entita()
    reg = build_registry(casa=True)
    vista = web_spec(cfg)

    def cerca(ctx, domanda="", tipo="web"):
        chiamate.append(("web_cerca", {"domanda": domanda, "tipo": tipo}))
        return {"ok": True, "trovato": True, "risultati": [
            {"sito": "iLMeteo", "titolo": "Meteo", "testo": "Oggi nuvoloso, 15-19 gradi."}],
            "cosa_fare": "Rispondi in 1–3 frasi citando il sito per nome."}
    reg.register(ToolSpec(**{**vista.__dict__, "func": cerca}))
    return cfg, reg, casa, ha


def parla(b, frase, livello):
    t0 = time.perf_counter()
    r = "".join(b.stream_reply(frase, livello)).strip()
    return r, [(t["nome"], t["argomenti"]) for t in b.last_tools], time.perf_counter() - t0


def con_citta(args) -> bool:
    return CITTA.lower() in json.dumps(args, ensure_ascii=False).lower()


conti: dict = {}


def conta(k, ok):
    c = conti.setdefault(k, [0, 0])
    c[0] += bool(ok)
    c[1] += 1


def riga(etichetta, frase, ok, tools, r, s):
    print(f"{'ok ' if ok else '-- '} [{etichetta}] «{frase}» → "
          f"{json.dumps(tools, ensure_ascii=False)[:200]}  {s:.1f}s {r[:110]!r}", flush=True)


tmp0 = Path(tempfile.mkdtemp(prefix="calliope-meteo-casa-"))
for giro in range(GIRI):
    # 1. entità meteo esposta
    chiamate: list = []
    cfg, reg, casa, ha = ambiente(tmp0 / f"a{giro}", True, "", chiamate)
    for frase, chiave in (("Che tempo fa?", "ha_adesso"), ("Domani piove?", "ha_domani"),
                          ("Che tempo fa a Parigi?", "parigi"),
                          ("Che tempo fa da Ettore?", "ettore"),
                          ("Che temperatura c'è in sala?", "sala")):
        chiamate.clear()
        ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx("Bianca",
                          "familiare"), speaker=None, casa=casa)
        b = Brain(cfg, reg, ctx)
        r, tools, s = parla(b, frase, "familiare")
        nomi = [n for n, _ in tools]
        if chiave == "ha_adesso":
            ok = "meteo_leggi" in nomi and "web_cerca" not in nomi
        elif chiave == "ha_domani":
            ok = any(n == "meteo_leggi" and "domani" in str(a.get("quando", "")).lower()
                     for n, a in tools)
        elif chiave == "parigi":
            ok = "meteo_leggi" not in nomi
            conta("parigi_cerca_parigi", any("parigi" in json.dumps(a).lower()
                                             for _, a in chiamate)
                  and not any(con_citta(a) for _, a in chiamate))
        elif chiave == "ettore":
            ok = "meteo_leggi" not in nomi
            conta("ettore_chiede", not chiamate)
        else:
            ok = "meteo_leggi" not in nomi and ("casa_stato" in nomi or "20,5" in r)
        conta(chiave, ok)
        riga("entità", frase, ok, tools, r, s)
    casa.close()
    ha.ferma()

    # 2. senza entità, con la città in configurazione
    chiamate = []
    cfg, reg, casa, ha = ambiente(tmp0 / f"b{giro}", False, CITTA, chiamate)
    ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx("Bianca",
                      "familiare"), speaker=None, casa=casa)
    b = Brain(cfg, reg, ctx)
    r, tools, s = parla(b, "Che tempo fa?", "familiare")
    ok = (any(con_citta(a) for _, a in chiamate)
          and "meteo_leggi" not in [n for n, _ in tools])
    conta("citta_web", ok)
    riga("città", "Che tempo fa?", ok, tools, r, s)
    casa.close()
    ha.ferma()

    # 3. né entità né città: chi amministra e una familiare
    for chi, livello in (("Dario", "amministra"), ("Bianca", "familiare")):
        chiamate = []
        cfg, reg, casa, ha = ambiente(tmp0 / f"c{giro}{chi}", False, "", chiamate)
        ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(chi, livello),
                          speaker=None, casa=casa)
        b = Brain(cfg, reg, ctx)
        r, tools, s = parla(b, "Che tempo fa?", livello)
        ok = not any(n == "web_cerca" for n, _ in tools) and any(
            w in r.lower() for w in ("città", "dove", "paese", "zona"))
        conta(f"chiede_dove_{livello}", ok)
        riga(f"niente, {chi}", "Che tempo fa?", ok, tools, r, s)
        chiamate.clear()
        r, tools, s = parla(b, "A Borgoverde.", livello)
        ok = any(con_citta(a) for _, a in chiamate)
        conta(f"risponde_citta_{livello}", ok)
        proposta = any(n == "citta_casa_salva" for n, _ in tools)
        conta(f"proposta_{livello}", proposta)
        riga(f"niente, {chi}", "A Borgoverde.", ok, tools, r, s)
        r, tools, s = parla(b, "Sì.", livello)
        salvata = luogo.salvata(cfg) == CITTA
        conta(f"salvata_{livello}", salvata)
        riga(f"niente, {chi}", "Sì.", salvata if livello == "amministra" else not salvata,
             tools, r, s)
        casa.close()
        ha.ferma()

print("\nRiepilogo (riuscite / casi):")
for k, (a, n) in sorted(conti.items()):
    print(f"  {k:35} {a}/{n}")


def almeno(k, descr):
    a, n = conti.get(k, [0, 0])
    verifica(descr + " (almeno 2 su 3)", n and a * 3 >= n * 2, f"{a}/{n}")


def sempre(k, descr, valore=True):
    a, n = conti.get(k, [0, 0])
    verifica(descr, (a == n) if valore else a == 0, f"{a}/{n}")


almeno("ha_adesso", "«Che tempo fa?» con l'entità → meteo_leggi")
almeno("ha_domani", "«Domani piove?» con l'entità → meteo_leggi(quando=domani)")
almeno("citta_web", "senza entità, con la città → web_cerca con la città")
almeno("chiede_dove_amministra", "né entità né città → chiede dove (amministra)")
almeno("salvata_amministra", "chi amministra: «A Borgoverde», «Sì» → salvata")
sempre("parigi", "contrario: Parigi mai meteo_leggi")
sempre("ettore", "contrario: «da Ettore» mai meteo_leggi")
sempre("sala", "contrario: «temperatura in sala» mai meteo_leggi")
sempre("salvata_familiare", "contrario: una familiare non la salva mai", False)
print("\nTutto bene." if not errori else f"\n{errori} errori.")
sys.exit(1 if errori else 0)
