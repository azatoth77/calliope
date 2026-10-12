import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della scelta dei tool come metrica (12/10/2026, calliope/scelta_tool.py, punto 1
di docs/ricerche/2026-10-10-scelta-dei-tool.md).

Dai turni del registro: nomi inventati (corretti da Brain con il nome scritto, o senza un tool
vicino con «cosa si voleva» dalla chiamata riuscita dopo; nei turni di prima le sole regole),
correzioni riuscite al giro dopo, giri esauriti, ripieghi (regola o «Non ci sono riuscita»),
richieste ripetute della stessa persona entro 90 s (contrari: un'altra persona, troppo tardi,
un'altra frase, un turno senza parole), indice e avviso (contrario: pochi turni con tool), la
sezione in `calliope stato --turni` (testo e JSON); Brain segna il nome inventato. ~1 s.
"""

import contextlib
import io
import json
import shutil
import tempfile
from pathlib import Path

from calliope import scelta_tool as S

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    print(("OK  " if ok else "ERR ") + nome + ("" if ok else f"  → {dettaglio}"))
    if not ok:
        errori += 1


G = "2026-10-12"


def t(ora, testo, chi="p-ada", tool=(), regole=(), risposta="Fatto.", esito="risposta"):
    return {"inizio": f"{G}T{ora}", "esito": esito, "testo": testo, "risposta": risposta,
            "voce": {"nome": "Ada", "id": chi, "modo": "voce"} if chi else None,
            "tool": list(tool), "regole": list(regole)}


turni = [
    # corretto da Brain: scritto sviluppo_ferma, vero sviluppo_passo
    t("10:00:00", "ferma lo sviluppo", tool=[{"nome": "sviluppo_passo", "ok": True,
                                              "nome_inventato": "sviluppo_ferma"}],
      regole=["tool_nome_azione"]),
    # senza un tool vicino: si voleva quello riuscito dopo
    t("10:05:00", "com'è messo lo sviluppo", tool=[
        {"nome": "sviluppo_stato", "ok": False, "sconosciuto": True},
        {"nome": "lavoro_stato", "ok": True}]),
    # correzione riuscita al giro dopo
    t("10:10:00", "cerca le notizie", tool=[
        {"nome": "web_cerca", "ok": False, "correggibile": True, "errore": "manca domanda"},
        {"nome": "web_cerca", "ok": True}]),
    # correzione esaurita e ripiego
    t("10:20:00", "metti un timer", tool=[
        {"nome": "timer_imposta", "ok": False, "correggibile": True}],
      regole=["correzioni_esaurite", "vuoto_ripiego"],
      risposta="Non ci sono riuscita: puoi ripetere la richiesta?"),
    # ripetuta subito dopo, dalla stessa persona (dopo un ripiego)
    t("10:20:30", "metti un timer di cinque minuti", tool=[
        {"nome": "timer_imposta", "ok": True}]),
    # contrari delle ripetute: un'altra persona, troppo tardi, frase diversa, senza parole
    t("10:20:40", "metti un timer di cinque minuti", chi="p-bea"),
    t("10:30:00", "metti un timer di cinque minuti"),
    t("10:30:20", "che tempo fa domani a Lucca"),
    t("10:30:30", None),
    # turno di prima del 12/10: solo la regola
    t("10:40:00", "cancella il promemoria", tool=[{"nome": "agenda_annulla", "ok": True}],
      regole=["tool_nome_corretto"]),
    # ripiego dal solo testo
    t("10:50:00", "apri il file", tool=[{"nome": "pc_apri_file", "ok": False}],
      risposta="Non ci sono riuscita: il file non c'è."),
]
d = S.per_giorno(turni)[G]
inv = d["inventati"]
verifica("nomi inventati: due, uno corretto e uno senza un tool vicino",
         inv["n"] == 2 and inv["corretti"] == 1 and inv["senza_vicino"] == 1, str(inv))
verifica("cosa si voleva: dal nome vero o dalla chiamata riuscita dopo",
         {(x["scritto"], x["voluto"]) for x in inv["nomi"]}
         == {("sviluppo_ferma", "sviluppo_passo"), ("sviluppo_stato", "lavoro_stato")},
         str(inv["nomi"]))
verifica("turni di prima: le regole dei nomi contate", inv["regole"] == 2, str(inv))
c = d["correzioni"]
verifica("correzioni: 2, una riuscita al giro dopo, una esaurita",
         c["n"] == 2 and c["riuscite"] == 1 and c["esauriti"] == 1, str(c))
verifica("ripieghi: dalla regola e dal testo", d["ripieghi"] == 2, str(d["ripieghi"]))
rp = d["ripetute"]
verifica("ripetute: una sola (stessa persona, entro 90 s, dopo un ripiego)",
         rp["n"] == 1 and rp["dopo_tool"] == 1, str(rp))
verifica("indice: problemi ogni 100 turni con tool",
         d["problemi"] == 1 + 1 + 2 + 1 and d["con_tool"] == 7
         and d["indice"] == round(100 * 5 / 7, 1), str(d))
verifica("contrario: pochi turni con tool, niente avviso", S.avviso(d) is None)
PAROLE = ("luce", "timer", "spesa", "meteo", "agenda", "musica", "volume", "notizie", "ora",
          "data", "lista", "ricordo", "foto", "file", "schermo", "voce", "casa", "calcolo",
          "treno", "ricetta", "sveglia", "promemoria", "biblioteca", "documento", "gioco")
molti = [t(f"11:{i:02d}:00", f"{w} {w}{i} {PAROLE[(i + 7) % 25]}",
           tool=[{"nome": "ora_attuale", "ok": True}]) for i, w in enumerate(PAROLE)]
molti[3]["regole"] = ["correzioni_esaurite"]
molti[5]["regole"] = ["vuoto_ripiego"]
molti[7]["regole"] = ["nome_tool_ripetuto"]
d2 = S.giorno(molti)
verifica("avviso oltre la soglia con abbastanza turni con tool",
         d2["indice"] == 12.0 and S.avviso(d2) and "12.0 problemi" in S.avviso(d2), str(d2))
d3 = S.giorno(molti[:3] + [dict(x, regole=[]) for x in molti[3:]])
verifica("contrario: sotto la soglia, niente avviso", S.avviso(d3) is None, str(d3["indice"]))
verifica("somiglianza: riformulata sì, altra frase no",
         S.somiglianza("metti un timer", "metti un timer di cinque minuti") >= S.SOMIGLIANZA
         and S.somiglianza("metti un timer", "che tempo fa domani") < S.SOMIGLIANZA)
testo = S.testo(S.per_giorno(turni))
verifica("testo: i numeri e i nomi", "sviluppo_ferma → sviluppo_passo" in testo
         and "ripetute 1" in testo and "correzioni 2 (1 riuscite" in testo, testo)
verifica("registro vuoto: una riga", "nessun turno" in S.testo({}))

# In `calliope stato --turni`
tmp = Path(tempfile.mkdtemp(prefix="calliope-scelta-"))
vecchio = os.environ.get("CALLIOPE_TURN_LOG")
try:
    (tmp / f"turni-{G}.jsonl").write_text("\n".join(json.dumps(x) for x in turni) + "\n",
                                          encoding="utf-8")
    os.environ["CALLIOPE_TURN_LOG"] = str(tmp)
    from calliope import stato
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = stato.main(["--turni"])
    verifica("calliope stato --turni: la sezione della scelta dei tool",
             rc == 0 and "Scelta dei tool" in out.getvalue()
             and "sviluppo_stato → lavoro_stato" in out.getvalue(), out.getvalue()[-800:])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        stato.main(["--turni", "--json"])
    j = json.loads(out.getvalue()[out.getvalue().index("{"):])
    verifica("--json: scelta_tool per giorno", j["scelta_tool"][G]["inventati"]["n"] == 2)
finally:
    if vecchio is None:
        os.environ.pop("CALLIOPE_TURN_LOG", None)
    else:
        os.environ["CALLIOPE_TURN_LOG"] = vecchio
    shutil.rmtree(tmp, ignore_errors=True)

# Brain segna il nome scritto dal modello quando lo corregge
from calliope.brain import Brain
from calliope.tools.builtin import build_registry

b = Brain.__new__(Brain)
b.tools, b.last_rules = build_registry(), []
b._nome_inventato = None
call = {"id": "c1", "name": "orra_attuale", "arguments": {}}
b._nome_corretto(call)
verifica("Brain: nome corretto e nome inventato ricordato per il registro",
         call["name"] == "ora_attuale" and b._nome_inventato == "orra_attuale")
b._nome_inventato = None
call = {"id": "c2", "name": "accendi_tutto", "arguments": {}}
b._nome_corretto(call)
verifica("Brain, contrario: un nome lontano non è «corretto»", b._nome_inventato is None)

print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
