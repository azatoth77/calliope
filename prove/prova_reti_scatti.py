import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco del rapporto degli scatti delle reti (15/10/2026, roadmap 2.11, E11,
calliope/reti_scatti.py, `calliope stato --reti`).

L'inventario: ogni rete del modello di config.RETI ha le sue regole e il suo posto, ogni regola
elencata è scritta davvero nel codice (un nome cambiato diventerebbe una falsa «mai scattata»),
nessuna regola sta sotto due reti, ogni nome passato a `_net`/`cfg.rete` è in RETI. Su un
registro finto: scatti e osservati per profilo, accesa dal campo `reti_spente` o dedotta dal
profilo nei turni di prima, «tutte», le risposte di prima che la rete fosse nel codice non
contano, ultima volta, esito dopo lo scatto (bene, ripiego, giri esauriti, ripetuta e
interrotta dalla stessa persona entro 90 s, con i contrari: un'altra persona, troppo tardi,
senza parole), tool riuscito, aiuto usato, MAI SCATTATA con e senza pochi turni, spenta; le
reti spente adesso dal profilo e nel locale; TurnLog che scrive `reti_spente` anche vuota;
la sezione di `calliope stato --reti` in testo e JSON. ~1 s.
"""

import contextlib
import io
import json
import re
import shutil
import tempfile
import types
from pathlib import Path

from calliope import reti_scatti as R
from calliope.config import MODELLO, PROFILI_LLM, RETI, reti_di

errori = 0
RADICE = Path(__file__).resolve().parent.parent


def verifica(nome, ok, dettaglio=""):
    global errori
    print(("OK  " if ok else "ERR ") + nome + ("" if ok else f"  → {dettaglio}"))
    if not ok:
        errori += 1


# ── 1. inventario ──
modello = set(reti_di(MODELLO))
verifica("ogni rete del modello ha le sue regole", modello == set(R.REGOLE_RETE),
         f"mancano {modello - set(R.REGOLE_RETE)}, in più {set(R.REGOLE_RETE) - modello}")
verifica("ogni rete del modello ha il suo posto nel codice", modello == set(R.DOVE),
         f"{modello ^ set(R.DOVE)}")
verifica("NEL_CODICE_DAL solo per reti vere", set(R.NEL_CODICE_DAL) <= modello)
codice = "".join(p.read_text(encoding="utf-8") for p in (RADICE / "calliope").rglob("*.py")
                 if p.name != "reti_scatti.py")
tutte = [(rete, r) for d in (R.REGOLE_RETE, R.SEGUITI, R.ESITO_CATTIVO)
         for rete, regole in d.items() for r in regole]
assenti = [r for _, r in tutte if f'"{r}"' not in codice]
verifica("ogni regola elencata è scritta nel codice", not assenti, f"{assenti}")
viste: dict = {}
doppie = []
for rete, regole in R.REGOLE_RETE.items():
    for r in regole:
        if r in viste:
            doppie.append((r, viste[r], rete))
        viste[r] = rete
verifica("nessuna regola sotto due reti", not doppie, f"{doppie}")
nomi_net = set(re.findall(r"""(?:_net|\.rete)\(\s*["']([a-z_]+)["']""", codice))
verifica("ogni nome passato a _net o cfg.rete è in RETI", nomi_net <= set(RETI),
         f"{nomi_net - set(RETI)}")
verifica("e nel codice ci sono quasi tutte le reti del modello",
         len(modello & nomi_net) >= len(modello) - 1, f"{modello - nomi_net}")

# ── 2. registro finto ──
P26, P4 = "gemma4-26b-ollama", "gemma4-e4b-ollama"
SP26 = list(PROFILI_LLM[P26]["llm_reti_spente"])


def t(giorno, ora, regole=(), chi="p-ada", testo="Accendi la luce.", esito="risposta",
      profilo=P26, spente=None, tool=(), risposta="Fatto."):
    r = {"inizio": f"2026-10-{giorno}T{ora}", "esito": esito, "testo": testo,
         "risposta": risposta, "regole": list(regole), "profilo": profilo,
         "modello": "finto", "tool": list(tool),
         "voce": {"nome": "Ada", "id": chi} if chi else None}
    if spente is not None:
        r["reti_spente"] = list(spente)
    return r


turni = [
    # prima del 15/10: niente reti_spente, dedotte dal profilo del 26B
    t("10", "10:00:00", ["spinta_dichiarata"], tool=[{"nome": "casa_comando", "ok": True}]),
    t("10", "10:00:30", testo="Che ore sono?"),                    # altra frase: bene
    t("10", "11:00:00", ["dichiarata_taciuta"], testo="Spegni la tv."),   # ripiego
    t("10", "11:00:20", ["eco_contesto"], testo="Spegni la tv adesso."),
    t("10", "11:00:40", testo="Spegni la tv adesso!"),             # ripetuta dopo l'eco
    t("10", "12:00:00", ["textcallguard"], testo="Metti un timer."),
    t("10", "12:00:10", esito="interruzione", testo="Basta."),     # interrotta
    t("10", "13:00:00", ["correzione_tool", "correzioni_esaurite"]),       # esito cattivo
    t("10", "14:00:00", ["argomento_forse"], testo="Chiama Patello."),
    t("10", "14:00:20", ["argomento_forse_usato"], testo="Chiama Pastello."),
    t("10", "15:00:00", ["riferimento_casa"], chi="p-ada", testo="Accendila."),
    t("10", "15:00:30", testo="Accendila.", chi="p-bea"),          # altra persona: bene
    t("10", "16:00:00", ["riferimento_agenda"], testo="Spostalo."),
    t("10", "16:05:00", testo="Spostalo."),                        # troppo tardi: bene
    t("10", "17:00:00", ["spinta_rinuncia"], testo=None, chi="p-minore"),  # senza parole
    t("10", "17:00:20", testo=None, chi="p-minore"),
    # dal 15/10: reti_spente nel turno (il locale spegne anche eco_contesto)
    t("15", "09:00:00", ["domanda_insistita"], spente=SP26 + ["eco_contesto"]),
    t("15", "09:01:00", spente=SP26 + ["eco_contesto"], testo="Altro."),
    # profilo del 4B: tutto acceso, spinta_promessa scatta
    t("12", "09:00:00", ["spinta_promessa", "spinta_promessa"], profilo=P4, spente=[]),
    t("12", "09:10:00", profilo=P4, spente=["tutte"], testo="Ciao."),
    # turno senza risposta del modello: non osservato
    t("12", "10:00:00", esito="ignorato", profilo=P4, spente=[]),
]
r = R.riassunto(turni)
p26 = r["profili"][P26]["reti"]
p4 = r["profili"][P4]["reti"]
verifica("turni e giorni", r["turni"] == len(turni) and r["dal"] == "2026-10-10"
         and r["al"] == "2026-10-15", f"{r['turni']} {r['dal']} {r['al']}")
verifica("risposte del 26B", r["profili"][P26]["risposte"] == 17,
         r["profili"][P26]["risposte"])
d = p26["spinta_dichiarata"]
verifica("spinta_dichiarata: due scatti (anche dichiarata_taciuta)", d["scatti"] == 2
         and d["regole"] == {"spinta_dichiarata": 1, "dichiarata_taciuta": 1}, d)
verifica("spinta_dichiarata: un bene col tool riuscito, un ripiego",
         d["bene"] == 1 and d["dubbi"]["ripiego"] == 1 and d["tool_riuscito"] == 1, d)
verifica("osservati: le risposte del 26B con la rete accesa", d["osservati"] == 17, d["osservati"])
verifica("ultima volta", d["ultima"] == "2026-10-10T11:00:00", d["ultima"])
e = p26["eco_contesto"]
verifica("ripetuta dalla stessa persona entro 90 s: dubbio", e["dubbi"]["ripetuta"] == 1
         and e["bene"] == 0, e)
verifica("spenta nel locale (reti_spente del turno): non osservata", e["osservati"] == 15
         and e["spenta_turni"] == 2, f"{e['osservati']} {e['spenta_turni']}")
verifica("interrotta subito dopo: dubbio", p26["textcallguard"]["dubbi"]["interrotta"] == 1)
verifica("giri esauriti: dubbio della rete", p26["correzione_tool"]["dubbi"]["esito"] == 1)
af = p26["argomento_forse"]
verifica("argomento_forse: aiuto usato al turno dopo, e non è uno scatto",
         af["scatti"] == 1 and af["seguiti"] == 1, af)
verifica("altra persona dopo: bene", p26["riferimento_casa"]["bene"] == 1)
verifica("troppo tardi: bene", p26["riferimento_agenda"]["bene"] == 1)
sr = p26["spinta_rinuncia"]
verifica("senza parole: bene ma contato a parte", sr["bene"] == 1 and sr["senza_parole"] == 1, sr)
sp = p26["spinta_promessa"]
verifica("26B: spinta_promessa spenta dal profilo (dedotta) e dal turno",
         sp["osservati"] == 0 and sp["stato"] == "spenta", sp)
di = p26["domanda_insistita"]
verifica("rete nata il 15/10: osservate solo le risposte da quel giorno",
         di["scatti"] == 1 and di["osservati"] == 2, di)
verifica("26B: ciclo_ripetuto mai scattata, pochi turni",
         p26["ciclo_ripetuto"]["stato"] == "mai scattata (pochi turni)",
         p26["ciclo_ripetuto"]["stato"])
verifica("mai_scattate col minimo", "citazione_tolta" in R.mai_scattate(r, P26, 10)
         and "spinta_dichiarata" not in R.mai_scattate(r, P26, 10)
         and "spinta_promessa" not in R.mai_scattate(r, P26, 10)
         and not R.mai_scattate(r, P26))
verifica("4B: spinta_promessa scatta (un turno, due volte)", p4["spinta_promessa"]["scatti"] == 1
         and p4["spinta_promessa"]["volte"] == 2, p4["spinta_promessa"])
verifica("4B: «tutte» spegne, il turno ignorato non conta",
         p4["eco_contesto"]["osservati"] == 1 and p4["eco_contesto"]["spenta_turni"] == 1,
         p4["eco_contesto"])
verifica("accese dedotte e registrate", r["accese_dedotte"] == 15
         and r["accese_registrate"] == 4, f"{r['accese_dedotte']} {r['accese_registrate']}")
verifica("una rete di sicurezza è sempre accesa", R.accesa({"reti_spente": ["tutte"]}, "permessi"))

# MAI SCATTATA con abbastanza turni
molti = [t("11", f"{h:02d}:{m:02d}:00", testo=f"frase {h} {m}") for h in range(10, 20)
         for m in range(0, 60, 2)]
rm = R.riassunto(molti)
verifica("MAI SCATTATA con abbastanza risposte", rm["profili"][P26]["reti"]["textcallguard"]["stato"]
         == "mai scattata" and "textcallguard" in R.mai_scattate(rm, P26), len(molti))

# Le reti spente adesso: dal profilo e nel locale
cfg = types.SimpleNamespace(llm_profilo=P26, llm_model="gemma4:26b",
                            llm_reti_spente=SP26 + ["eco_contesto"])
ra = R.riassunto(turni, cfg)
verifica("spente dal profilo e nel locale", ra["adesso"]["spente_dal_profilo"] == SP26
         and ra["adesso"]["spente_nel_locale"] == ["eco_contesto"], ra["adesso"])
tx = R.testo(ra)
verifica("testo: profilo, MAI SCATTATA, locale, sicurezza",
         f"Profilo {P26}" in tx and "MAI SCATTATA" in tx and "spente nel locale: eco_contesto"
         in tx and "permessi" in tx and "dedotto dal profilo" in tx, tx[:400])
verifica("testo senza turni", "Nessun turno" in R.testo(R.riassunto([])))

# ── 3. TurnLog scrive reti_spente anche vuota, il profilo None no ──
from calliope.turnlog import TurnLog, read_turns  # noqa: E402
tmp = Path(tempfile.mkdtemp(prefix="reti_scatti_"))
try:
    tl = TurnLog(str(tmp / "a"), modello={"profilo": None, "modello": "m", "reti_spente": []})
    tl.write({"inizio": "2026-10-15T10:00:00", "esito": "risposta", "livello": "familiare"})
    rec = read_turns(str(tmp / "a"))[0]
    verifica("TurnLog: reti_spente vuota scritta, profilo None no",
             rec.get("reti_spente") == [] and "profilo" not in rec and rec["modello"] == "m", rec)

    # ── 4. calliope stato --reti ──
    from calliope import stato  # noqa: E402
    cart = tmp / "registro"
    cart.mkdir()
    with open(cart / "turni-2026-10-10.jsonl", "w", encoding="utf-8") as f:
        for x in turni:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
        f.write("{riga rotta\n")
    cfg.turn_log_dir = str(cart)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = stato.reti_main(cfg, ["--reti"], False)
    verifica("stato --reti: testo", rc == 0 and "MAI SCATTATA" in out.getvalue()
             and "spinta_dichiarata" in out.getvalue(), out.getvalue()[:300])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = stato.reti_main(cfg, ["--reti", "--giorni", "3", "--json"], True)
    j = json.loads(out.getvalue())
    verifica("stato --reti --json", rc == 0 and j["profili"][P26]["reti"]["spinta_dichiarata"]
             ["scatti"] == 2, out.getvalue()[:200])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = stato.reti_main(cfg, ["--reti", "--giorni", "x"], False)
    verifica("--giorni sbagliato", rc == 1 and "numero" in out.getvalue())
    verifica("l'aiuto di calliope stato nomina --reti", "--reti" in (stato.__doc__ or ""))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
print("Tutto bene." if not errori else f"{errori} errori.")
sys.exit(1 if errori else 0)
