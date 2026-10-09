import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco del meteo di casa (09/10, decisione di Dario: «il meteo senza indicazioni è
quello di casa»), con l'HA finto di prove/ha_finto.py e nomi di fantasia (la casa è a
Borgoverde).

1. Le condizioni di HA in italiano, i giorni chiesti (`quando`), il riassunto delle previsioni.
2. HA finto con un'entità `weather.*` esposta: meteo_esposte senza aspettare, meteo_leggi
   adesso, domani (giornaliere), stasera (orarie), per tutti i livelli (anche l'ospite), solo
   `weather.get_forecasts` chiamato, previsioni in cache; casa_stato per nome dice la
   condizione in italiano. Contrari: «temperatura in camera» resta il sensore della camera;
   l'entità meteo NON esposta non si vede e meteo_leggi dice cosa fare (città o domanda).
3. Il prompt di sistema secondo la disponibilità vera: entità esposta → meteo_leggi; solo la
   città → la frase della città; niente → «chiedi in che città è la casa»; configurazione
   vuota o segnaposto → come niente; cambia quando l'esposizione cambia.
4. La città salvata a voce (calliope/luogo.py): solo chi amministra, prima la proposta e poi
   «conferma»; familiare e ospite no; luogo.json accanto alla configurazione, mai
   calliope.yaml; la configurazione vince; la politica (classi dichiarate, proposta innocua).

    python prove\\prova_meteo_casa.py
"""

import datetime as dt
import json
import time
from pathlib import Path

from prove.ha_finto import TOKEN, FakeHA, _e, cartella_temporanea, disponibile, entita_casa

manca = disponibile()
if manca:
    print(f"SALTO: per l'HA finto manca {manca}")
    sys.exit(77)

os.environ.pop("CALLIOPE_HA_TOKEN", None)

from calliope import luogo, politica                                    # noqa: E402
from calliope.brain import Brain                                        # noqa: E402
from calliope.casa import load_casa                                     # noqa: E402
from calliope.casa import meteo as M                                    # noqa: E402
from calliope.config import Config                                      # noqa: E402
from calliope.tools.builtin import build_registry                       # noqa: E402
from calliope.tools.spec import ToolContext                             # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


class SpeakerCtx:
    def __init__(self, name, level, come="voce"):
        self.current_speaker, self.current_level, self.from_session = name, level, False
        self.identified_by, self.profile_level = come, level


TMP = Path(cartella_temporanea())


def cfg_nuova(url=None, citta="") -> Config:
    d = TMP / f"c{len(list(TMP.iterdir()))}"
    d.mkdir()
    c = Config()
    c.config_dir = str(d)
    c.casa_url = url
    c.casa_timeout_s = 1.0
    c.casa_connessione_s = 1.0
    c.casa_citta = citta
    if url:
        (d / "segreti.yaml").write_text(f'home_assistant:\n  token: "{TOKEN}"\n',
                                        encoding="utf-8")
    return c


# ─────────────────────────── 1. condizioni, giorni, riassunto ───────────────────────────
print("— condizioni e giorni")
verifica("condizioni in italiano", M.condizione("partlycloudy") == "parzialmente nuvoloso"
         and M.condizione("rainy") == "pioggia" and M.condizione("clear-night") == "sereno"
         and M.condizione("snowy-rainy") == "pioggia mista a neve")
verifica("tutte le 15 condizioni di HA tradotte", len(M.CONDIZIONI) == 15
         and all("-" not in v and v for v in M.CONDIZIONI.values()))
verifica("condizione detta: «c'è nebbia», «è nuvoloso»",
         M.condizione_detta("fog") == "c'è nebbia" and M.condizione_detta("cloudy") == "è nuvoloso")
verifica("condizione sconosciuta: senza trattini", M.condizione("strano-tempo") == "strano tempo")
oggi = dt.date(2026, 10, 9)                               # un venerdì
G = M.giorni_chiesti
verifica("«» e «adesso» → meteo di adesso", G("", oggi) == ([], None)
         and G("adesso", oggi) == ([], None))
verifica("«domani» → sabato 10", G("domani", oggi) == ([dt.date(2026, 10, 10)], None))
verifica("«dopodomani»", G("dopodomani", oggi)[0] == [dt.date(2026, 10, 11)])
verifica("«stasera» → oggi, 18–24", G("stasera", oggi) == ([oggi], (18, 24)))
verifica("«domani mattina» → domani, 6–12", G("domani mattina", oggi)
         == ([dt.date(2026, 10, 10)], (6, 12)))
verifica("«martedì» → il prossimo martedì", G("martedì", oggi)[0] == [dt.date(2026, 10, 13)])
verifica("«venerdì» detto di venerdì → oggi", G("venerdì", oggi)[0] == [oggi])
verifica("«weekend» → sabato e domenica", G("weekend", oggi)[0]
         == [dt.date(2026, 10, 10), dt.date(2026, 10, 11)])
verifica("«prossimi giorni» → 5 giorni", len(G("prossimi giorni", oggi)[0]) == 5)
r = M.riassumi_giorno([{"condition": "rainy", "temperature": 18, "templow": 12,
                        "precipitation": 4.2, "precipitation_probability": 80}])
verifica("riassunto di un giorno", r["cielo"] == "pioggia" and r["massima"] == 18
         and r["minima"] == 12 and r["probabilita_pioggia"] == 80, str(r))
f = M.frase_giorno("domani, sabato 10", r)
verifica("frase del giorno", f == "Domani, sabato 10: pioggia, tra 12 e 18 gradi, probabilità "
         "di pioggia 80 per cento.", f)


# ─────────────────────────── 2. HA finto con l'entità meteo ───────────────────────────
print("— Home Assistant con l'entità meteo esposta")


def iso(giorno: dt.date, ora: int) -> str:
    # ora locale → ISO con il fuso della macchina (come HA, che manda UTC)
    t = dt.datetime(giorno.year, giorno.month, giorno.day, ora).astimezone()
    return t.astimezone(dt.timezone.utc).isoformat()


oggi_vero = dt.date.today()
domani = oggi_vero + dt.timedelta(days=1)
METEO = _e("weather.forecast_casa", "Forecast Casa", None, "partlycloudy",
           attr={"temperature": 17.4, "humidity": 71, "wind_speed": 12.6,
                 "temperature_unit": "°C", "wind_speed_unit": "km/h", "pressure": 1015,
                 "supported_features": 3})
NASCOSTA = _e("weather.altrove", "Meteo altrove", None, "sunny", esposta=False,
              attr={"temperature": 30, "supported_features": 1})
ha = FakeHA(entita=entita_casa() + [METEO, NASCOSTA]).avvia()
ha.previsioni[("weather.forecast_casa", "daily")] = [
    {"datetime": iso(oggi_vero, 12), "condition": "partlycloudy", "temperature": 19,
     "templow": 11},
    {"datetime": iso(domani, 12), "condition": "rainy", "temperature": 16, "templow": 12,
     "precipitation": 6.1, "precipitation_probability": 85, "wind_speed": 22},
]
ha.previsioni[("weather.forecast_casa", "hourly")] = [
    {"datetime": iso(oggi_vero, h), "condition": "cloudy" if h < 20 else "rainy",
     "temperature": 15 - (h - 18) * 0.5, "precipitation_probability": 40 if h < 20 else 70}
    for h in range(18, 24)] + [
    {"datetime": iso(oggi_vero, 10), "condition": "sunny", "temperature": 20}]
cfg = cfg_nuova(ha.url)
be, diag = load_casa(cfg)
verifica("collegata", be is not None and be.attendi_primo_tentativo(3.0))
be.entita()
verifica("meteo_esposte: solo l'entità esposta, senza aspettare",
         be.meteo_esposte() == ["weather.forecast_casa"], str(be.meteo_esposte()))
from calliope.tools.casa import allinea_meteo, meteo_spec  # noqa: E402
reg = build_registry(casa=True, web=True)
verifica("senza allineare, meteo_leggi non c'è", reg.get("meteo_leggi") is None)
verifica("allinea_meteo con l'entità esposta: meteo_leggi registrato",
         allinea_meteo(reg, be) and not allinea_meteo(reg, be))
names = [s["function"]["name"] for s in reg.all_schemas()]
verifica("tool meteo_leggi e citta_casa_salva nel registro",
         "meteo_leggi" in names and "citta_casa_salva" in names)
verifica("politica: classi dichiarate", politica.classe_di("meteo_leggi").dichiarata
         and politica.classe_di("citta_casa_salva").dichiarata
         and politica.classe_di("meteo_leggi").classe == politica.SICURO)


def ctx_per(c, casa, chi="Bianca", livello="familiare"):
    return ToolContext(cfg=c, speakers=None, speaker_ctx=SpeakerCtx(chi, livello),
                       speaker=None, casa=casa)


def chiama(c, casa, nome, args, livello="familiare", chi="Bianca", ctx=None):
    ctx = ctx or ctx_per(c, casa, chi, livello)
    return json.loads(reg.call(nome, args, ctx, livello)), ctx


r, ctx = chiama(cfg, be, "meteo_leggi", {})
verifica("adesso: cielo, gradi, umidità, vento in italiano",
         r.get("ok") and r["frase"] == "A casa adesso è parzialmente nuvoloso, 17,4 gradi, "
         "umidità al 71 per cento, vento a 12,6 chilometri orari.", r.get("frase", str(r)))
verifica("adesso: nessuna richiesta di servizi", ha.chiamate_servizi == [])
verifica("i dati per il modello e cosa fare", r["adesso"]["temperatura"] == 17.4
         and "Home Assistant" in r["cosa_fare"])
r, _ = chiama(cfg, be, "meteo_leggi", {"quando": "domani"})
verifica("domani: previsioni giornaliere", r.get("ok") and r["previsioni"][0]["cielo"] ==
         "pioggia" and "probabilità di pioggia 85 per cento" in r["frase"]
         and r["frase"].startswith("Domani"), r.get("frase", str(r)))
verifica("solo weather.get_forecasts, con la risposta",
         ha.chiamate_servizi == [("weather", "get_forecasts", "weather.forecast_casa", "daily",
                                  True)], str(ha.chiamate_servizi))
r, _ = chiama(cfg, be, "meteo_leggi", {"quando": "domani"})
verifica("previsioni in cache: nessuna seconda richiesta", len(ha.chiamate_servizi) == 1)
r, _ = chiama(cfg, be, "meteo_leggi", {"quando": "stasera"})
verifica("stasera: previsioni orarie della sera (18–24), non quella delle 10",
         r.get("ok") and ha.chiamate_servizi[-1][3] == "hourly"
         and r["previsioni"][0]["probabilita_pioggia"] == 70 and r["previsioni"][0]["massima"] == 15,
         str(r.get("previsioni")))
lontano = M.GIORNI[(oggi_vero + dt.timedelta(days=4)).weekday()]   # senza previsioni
r, _ = chiama(cfg, be, "meteo_leggi", {"quando": lontano})
verifica("un giorno senza previsioni: lo dice, e niente internet né città",
         not r.get("ok") and "non ha previsioni" in r.get("cosa_fare", "")
         and "città" not in r.get("cosa_fare", ""), str(r)[:300])
r, _ = chiama(cfg, be, "meteo_leggi", {}, livello="ospite", chi=None)
verifica("anche l'ospite ha il meteo di casa", r.get("ok"), str(r)[:120])
r, _ = chiama(cfg, be, "casa_stato", {"cosa": "forecast casa"})
verifica("casa_stato per nome: la condizione in italiano",
         "parzialmente nuvoloso" in r.get("risposta_finale", "")
         and "partlycloudy" not in r.get("risposta_finale", ""), r.get("risposta_finale"))
c_ctx = ctx_per(cfg, be)
c_ctx.user_text = "che temperatura c'è in camera?"
r, _ = chiama(cfg, be, "casa_stato", {"cosa": "temperatura in camera"}, ctx=c_ctx)
verifica("contrario: «temperatura in camera» è il sensore, non il meteo",
         "19,8" in r.get("risposta_finale", "") and "nuvoloso" not in r.get(
             "risposta_finale", ""), r.get("risposta_finale"))
verifica("l'entità meteo non esposta non si vede mai",
         all(e.id != "weather.altrove" for e in be.entita()))
try:
    be.previsioni("weather.altrove")
    verifica("previsioni di un'entità non esposta: rifiutate", False)
except ValueError:
    verifica("previsioni di un'entità non esposta: rifiutate", True)


# ─────────────────────────── 3. il prompt secondo la disponibilità ───────────────────────────
print("— il prompt di sistema")


def prompt(c, casa, registro=reg):
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = c, registro, []
    b.tool_ctx = ctx_per(c, casa)
    return b._system_messages()[0]["content"]


p = prompt(cfg, be)
verifica("entità esposta: meteo_leggi nel prompt, internet per gli altri posti",
         "chiedilo a meteo_leggi" in p and "Per il meteo di altri posti" in p)
verifica("entità esposta, senza città: niente «chiedi in che città»",
         "chiedi in che città" not in p)
cfg_c = cfg_nuova(ha.url, citta="Borgoverde")
p = prompt(cfg_c, be)
verifica("entità e città: la città resta per orari e negozi, il meteo a HA",
         "chiedilo a meteo_leggi" in p and "La casa dove sei è a Borgoverde" in p
         and "(orari, negozi, eventi)" in p)
ha2 = FakeHA(entita=entita_casa() + [NASCOSTA]).avvia()       # nessuna entità meteo esposta
cfg2 = cfg_nuova(ha2.url, citta="Borgoverde")
be2, _ = load_casa(cfg2)
be2.attendi_primo_tentativo(3.0)
be2.entita()
p = prompt(cfg2, be2)
verifica("senza entità esposta, con la città: la frase della città con il meteo",
         "meteo_leggi" not in p and "La casa dove sei è a Borgoverde" in p
         and "(meteo, orari, negozi, eventi)" in p and "Per il meteo, le notizie" in p)
verifica("senza entità esposta: meteo_leggi tolto dal registro",
         reg.get("meteo_leggi") is None)
reg.register(meteo_spec())               # una chiamata a cavallo del cambio: cosa fare
r, _ = chiama(cfg2, be2, "meteo_leggi", {})
verifica("meteo_leggi senza entità esposta: la città di casa nel cosa_fare",
         not r.get("ok") and "Borgoverde" in r.get("cosa_fare", ""), str(r)[:200])
for valore in ("", "  ", "<città>", "TODO", "la tua città", "[citta]"):
    c = cfg_nuova(ha2.url, citta=valore)
    p = prompt(c, be2)
    verifica(f"configurazione {valore!r}: si chiede dove si trova la casa",
             "Non sai in che città è la casa" in p and "citta_casa_salva" in p
             and "La casa dove sei" not in p)
reg.register(meteo_spec())
r, _ = chiama(cfg_nuova(ha2.url, citta="<città>"), be2, "meteo_leggi", {})
verifica("meteo_leggi senza entità né città: chiedere dove", "chiedi" in r.get("cosa_fare", ""))
verifica("contrario: «Città di Castello» è una città", luogo.valida("Città di Castello")
         == "Città di Castello")
verifica("contrario: «San Giorgio a Cremano» è una città",
         luogo.valida(" San Giorgio  a Cremano ") == "San Giorgio a Cremano")
reg_senza = build_registry(casa=True)                         # senza web né estensioni
p = prompt(cfg_nuova(), None, reg_senza)
verifica("senza web, estensioni, entità né città: niente domanda sulla città",
         "Non sai in che città" not in p and "Non puoi sapere meteo e notizie" in p)
p = prompt(cfg, be, reg_senza)
verifica("senza web, con l'entità meteo: «non puoi sapere» solo il resto",
         "Non puoi sapere le notizie né il meteo di altri posti" in p
         and "chiedilo a meteo_leggi" in p)
p_prima = prompt(cfg, be)
ha.entita["weather.forecast_casa"]["esposta"] = False          # chi amministra la nasconde
be._caricato = 0
be.entita()                                                    # ricarica in secondo piano
for _ in range(50):
    if not be.meteo_esposte():
        break
    time.sleep(0.05)
p_dopo = prompt(cfg, be)
verifica("esposizione tolta in HA: il prompt cambia da solo",
         "meteo_leggi" in p_prima and "meteo_leggi" not in p_dopo)
be_giu = be2
ha2.ferma()
time.sleep(0.2)
t0 = time.perf_counter()
p = prompt(cfg2, be_giu)
verifica("HA spento: il prompt non aspetta", time.perf_counter() - t0 < 0.2,
         f"{time.perf_counter() - t0:.3f}s")


# ─────────────────────────── 4. la città salvata a voce ───────────────────────────
print("— la città di casa salvata a voce")
c3 = cfg_nuova()
yaml_prima = sorted(os.listdir(c3.config_dir))
r, _ = chiama(c3, None, "citta_casa_salva", {"citta": "Borgoverde"}, livello="familiare")
verifica("familiare: non la salva e non la propone", not r.get("ok") and "in_sospeso" not in r
         and luogo.salvata(c3) == "", str(r)[:200])
r, _ = chiama(c3, None, "citta_casa_salva", {"citta": "Borgoverde", "conferma": True},
              livello="ospite", chi=None)
verifica("ospite con conferma: non la salva", luogo.salvata(c3) == "", str(r)[:200])
r, _ = chiama(c3, None, "citta_casa_salva", {"citta": "Borgoverde"}, livello="amministra",
              chi="Dario")
verifica("chi amministra, senza conferma: la proposta, niente salvato",
         r.get("in_sospeso", {}).get("argomenti") == {"citta": "Borgoverde", "conferma": True}
         and r["in_sospeso"]["domanda"].endswith("?") and luogo.salvata(c3) == "", str(r)[:300])
ctx_si = ctx_per(c3, None, "Dario", "amministra")
ctx_si.tool_in_sospeso = "citta_casa_salva"                    # il «sì» alla proposta
verifica("la proposta è innocua per la politica",
         politica.classe_di("citta_casa_salva").innocua({"citta": "Borgoverde"})
         and not politica.classe_di("citta_casa_salva").innocua({"citta": "Borgoverde",
                                                                 "conferma": True}))
r, _ = chiama(c3, None, "citta_casa_salva", {"citta": "<città>", "conferma": True},
              livello="amministra", chi="Dario", ctx=ctx_si)
verifica("segnaposto: non si salva", not r.get("ok") and luogo.salvata(c3) == "")
r, _ = chiama(c3, None, "citta_casa_salva", {"citta": "Borgoverde", "conferma": True},
              livello="amministra", chi="Dario")
verifica("contrario: conferma senza la proposta in sospeso → solo la proposta",
         "in_sospeso" in r and luogo.salvata(c3) == "", str(r)[:200])
r, _ = chiama(c3, None, "citta_casa_salva", {"citta": "Borgoverde", "conferma": True},
              livello="amministra", chi="Dario", ctx=ctx_si)
verifica("chi amministra, con conferma: salvata", r.get("ok") and luogo.salvata(c3) ==
         "Borgoverde" and "Borgoverde" in r.get("risposta_finale", ""), str(r)[:200])
verifica("salvata in luogo.json accanto alla configurazione, nient'altro",
         sorted(os.listdir(c3.config_dir)) == sorted(yaml_prima + ["luogo.json"]),
         str(os.listdir(c3.config_dir)))
verifica("luogo.json: città, chi, quando",
         json.loads(Path(c3.config_dir, "luogo.json").read_text(encoding="utf-8"))
         .get("da") == "Dario")
p = prompt(c3, None, build_registry(web=True))
verifica("la volta dopo «ci arriva da sola»: la città salvata nel prompt",
         "La casa dove sei è a Borgoverde" in p and "Non sai in che città" not in p)
verifica("origine: voce", luogo.origine(c3) == "voce")
c3.casa_citta = "Valfiorita"
verifica("la configurazione vince sulla città salvata", luogo.citta_casa(c3) == "Valfiorita"
         and luogo.origine(c3) == "configurazione")
r, _ = chiama(c3, None, "citta_casa_salva", {"citta": "Borgoverde", "conferma": True},
              livello="amministra", chi="Dario")
verifica("con la città in configurazione: a voce non si cambia",
         "configurazione" in r.get("nota", "") and luogo.salvata(c3) == "Borgoverde")
c4 = Config()
c4.config_dir = None
verifica("senza cartella di configurazione: nessun file (mai la cartella corrente)",
         luogo.percorso(c4) is None and luogo.salvata(c4) == "")

ha.ferma()
print("\nTutto bene." if not errori else f"\n{errori} errori.")
sys.exit(1 if errori else 0)
