"""Misura di `agenti_presence_penalty` per tipo di lavoro (11/10/2026, docs/aree/
agenti-estensioni.md, «Spinta concreta»). Da lanciare **sulla DGX quando è libera** (nessun
lavoro dell'agente in corso: usa lo stesso vLLM), nella cartella dei dati, con l'interprete
di Calliope:

    cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale) \\
        && $V/.venv/bin/python $V/prove/manuali/misura_presence_penalty.py \\
           [--valori 0,0.5,1,1.5] [--giri 6] [--tipo estensione] [--messaggio vecchio,nuovo]

Il caso è quello vero dell'11/10 («Halloween - Apri le porte», 45 minuti a vuoto): il prompt
vero del gioco (sistema, contratto, scheletro), la storia fino al primo esegui_test con la
prova di fumo che fallisce perché il gestore di «Inizia» lascia uscire l'eccezione della
logica, e poi **una passata** con gli strumenti veri, per ogni valore di presence_penalty e per
ogni forma del messaggio di fumo:
- «vecchio»: quello che l'agente ha visto davvero («tocco (click): Error: Devi inserire…»);
- «nuovo»: quello dell'11/10 (elemento, file:riga, la frase sul gestore, i fallimenti in breve).

Per ogni passata: se il rilevatore delle ripetizioni l'ha fermata (giro a vuoto, soglia
`agenti_ripetizioni_max`), la frase più ripetuta e quante volte, i token (ragionamento
compreso), i secondi, lo strumento scelto e se va al punto (modifica_file o leggi_file con
riga su logica.js/gioco.js, oppure scrivi_file di gioco.js con un try/catch nel gestore)
o riscrive il file intero. Alla fine una tabella per valore e messaggio. Non cambia la
configurazione né i file di nessuno: niente sandbox, nessuno strumento eseguito. Il predefinito
(0 per codice ed estensioni) si cambia solo se la tabella lo giustifica.
"""

import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from calliope.agenti.arbitro import Arbitro  # noqa: E402
from calliope.agenti.ciclo import (CHIEDI_PERMESSO, PIANO, SCARICA_ESEMPIO, Agente,  # noqa: E402
                                   Lavoro, strumenti_codice)
from calliope.agenti.impostazioni import carica  # noqa: E402
from calliope.agenti.remoto import crea_cliente  # noqa: E402
from calliope.agenti.ripetizioni import Ripetizioni  # noqa: E402
from calliope.config import load_config  # noqa: E402
from calliope.estensioni.prompt import sistema_estensione  # noqa: E402

argv = sys.argv[1:]


def opzione(nome, predefinito):
    return argv[argv.index(nome) + 1] if nome in argv else predefinito


VALORI = [float(x) for x in opzione("--valori", "0,0.5,1,1.5").split(",")]
GIRI = int(opzione("--giri", "6"))
TIPO = opzione("--tipo", "estensione")
MESSAGGI = opzione("--messaggio", "vecchio,nuovo").split(",")

COMPITO = ("Compito: un gioco sullo schermo a tema Halloween, «Apri le porte»: da 1 a 4 "
           "giocatori scrivono il nome, poi a turno aprono una porta e trovano un dolcetto "
           "(punti) o un mostro (punti in meno); vince chi ha più punti dopo tre turni.")
LOGICA = """"use strict";
const SORPRESE = [{ tipo: "dolce", punti: 10 }, { tipo: "mostro", punti: -10 }];
function creaStato(nomi) {
  if (!Array.isArray(nomi) || nomi.length < 1 || nomi.length > 4) {
    throw new Error("Devi inserire da 1 a 4 giocatori");
  }
  return { giocatori: nomi.map((n) => ({ nome: n, punti: 0 })), turno: 0, finita: false };
}
function apriPorta(stato, caso) {
  const s = SORPRESE[Math.floor(caso * SORPRESE.length)];
  const g = stato.giocatori.map((x, i) => i === stato.turno % stato.giocatori.length
    ? { ...x, punti: x.punti + s.punti } : x);
  const turno = stato.turno + 1;
  return { ...stato, giocatori: g, turno, finita: turno >= 3 * g.length };
}
if (typeof module !== "undefined") module.exports = { creaStato, apriPorta, SORPRESE };
"""
GIOCO = """"use strict";
const radice = document.getElementById("gioco");
let stato = null;
function avvia() {
  const nomi = [...radice.querySelectorAll("input")].map((i) => i.value.trim()).filter(Boolean);
  stato = creaStato(nomi);
  disegnaPorte();
}
function disegnaPorte() {
  radice.replaceChildren();
  for (let i = 0; i < 3; i++) {
    const p = document.createElement("button");
    p.textContent = "Porta " + (i + 1);
    p.addEventListener("click", () => { stato = apriPorta(stato, Math.random()); disegnaPorte(); });
    radice.appendChild(p);
  }
}
calliope.quandoPronto(() => {
  for (let i = 0; i < 4; i++) radice.appendChild(document.createElement("input"));
  const b = document.createElement("button");
  b.id = "inizia";
  b.textContent = "Inizia";
  b.addEventListener("click", () => avvia());
  radice.appendChild(b);
});
"""
TEST = """const { test } = require("node:test");
const assert = require("node:assert");
const { creaStato, apriPorta } = require("./logica.js");
test("stato nuovo", () => assert.strictEqual(creaStato(["Ottavio"]).turno, 0));
test("una porta", () => assert.strictEqual(apriPorta(creaStato(["Ottavio"]), 0).turno, 1));
"""
MANIFESTO = {"nome": "apri_le_porte", "titolo": "Apri le porte",
             "cosa_fa": {"verbo": "propone", "oggetto": "un gioco di Halloween con le porte"},
             "permessi": {}, "scheda": {"tipo": "gioco", "file": ["logica.js", "gioco.js"],
                                        "giocatori": {"min": 1, "max": 4}}}
ESITO = {"eseguiti": 3, "falliti": 1, "errori": 0, "saltati": 0}
# Quello che l'agente ha visto davvero l'11/10
VECCHIO = {"esito": ESITO, "passano": False, "uscita": (
    "ok stato nuovo\nok una porta\nFALLITO prova di fumo del gioco (gli script di «scheda.file» "
    "caricati con un DOM finto semplice e trecento tocchi a caso; se l'errore è di un metodo "
    "del DOM che il finto non conosce, scrivilo in un modo più comune): tocco (click): Error: "
    "Devi inserire da 1 a 4 giocatori")}
# Quello del codice dell'11/10 (prove/prova_agente_guida.py, stesso caso; righe di questo gioco)
_FUMO = ("tocco (click) su <button id=\"inizia\"> «Inizia»: Error: Devi inserire da 1 a 4 "
         "giocatori [in logica.js:5 (creaStato) ← gioco.js:6 (avvia) ← gioco.js:23]. Un gestore "
         "di evento ha lanciato un'eccezione: ogni gestore deve catturare gli errori della "
         "logica (try/catch) e mostrarli nel gioco, senza lasciarli uscire")
NUOVO = {"esito": ESITO, "passano": False, "fallimenti": (
    "prova di fumo del gioco: " + _FUMO.replace(" [in logica.js:5 (creaStato) ← gioco.js:6 "
                                                "(avvia) ← gioco.js:23]", "")
    + " (in logica.js:5 (creaStato) ← gioco.js:6 (avvia) ← gioco.js:23)"),
    "uscita": ("ok stato nuovo\nok una porta\nFALLITO prova di fumo del gioco: " + _FUMO
               + " — la prova carica gli script di «scheda.file» come nel riquadro (document "
               "finto con <div id=\"gioco\">, l'oggetto calliope, timer finti), chiama "
               "quandoPronto e tocca a caso gli elementi con un gestore; correggi il punto "
               "indicato, non riscrivere il file. Se l'errore è di un metodo del DOM che il "
               "finto non conosce, scrivilo in un modo più comune")}


def storia(cfg, messaggio: str) -> list:
    piano = {"capacita_necessarie": ["scheda"], "scope": {}, "fattibile": True,
             "motivo": "un gioco puro nel riquadro"}
    scritti = [("logica.js", LOGICA), ("gioco.js", GIOCO), ("logica.test.js", TEST),
               ("manifesto.json", json.dumps(MANIFESTO, ensure_ascii=False))]
    msgs = [{"role": "system", "content": sistema_estensione(cfg, gioco=True)},
            {"role": "user", "content": COMPITO},
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "piano", "arguments": piano}}]},
            {"role": "tool", "tool_name": "piano", "content": json.dumps(
                {"ok": True, "nota": "piano registrato: gioco puro"}, ensure_ascii=False)},
            {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "scrivi_file", "arguments": {"percorso": p,
                                                                   "contenuto": c}}}
                for p, c in scritti]}]
    for p, c in scritti:
        msgs.append({"role": "tool", "tool_name": "scrivi_file", "content": json.dumps(
            {"ok": True, "percorso": p, "righe": c.count("\n") + 1})})
    msgs += [{"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "esegui_test", "arguments": {}}}]},
             {"role": "tool", "tool_name": "esegui_test", "content": json.dumps(
                 VECCHIO if messaggio == "vecchio" else NUOVO, ensure_ascii=False)}]
    return msgs


def al_punto(chiamate) -> str:
    """Come risponde all'errore: «mirata», «riscrive», «legge», «altro», «nessuna»."""
    if not chiamate:
        return "nessuna"
    c = chiamate[0]
    nome, a = c.get("name"), c.get("arguments") or {}
    if isinstance(a, str):
        try:
            a = json.loads(a)
        except ValueError:
            a = {}
    if nome == "modifica_file":
        return "mirata"
    if nome == "leggi_file":
        return "legge" + (" (riga)" if a.get("riga") else "")
    if nome == "scrivi_file":
        testo = str(a.get("contenuto") or "")
        if str(a.get("percorso")) == "gioco.js" and "catch" in testo:
            return "riscrive (con try/catch)"
        return "riscrive"
    return nome or "altro"


def main():
    cfg = load_config()
    imp = carica(cfg)
    if imp is None or getattr(imp, "motore", "") != "openai":
        print("Serve l'agente su vLLM (motore openai): presence_penalty va solo lì.")
        return 2
    cliente = crea_cliente(imp)
    strumenti = [PIANO, CHIEDI_PERMESSO] + strumenti_codice(["python"]) + [SCARICA_ESEMPIO]
    righe = []
    for messaggio in MESSAGGI:
        for v in VALORI:
            cfg.agenti_presence_penalty = {TIPO: v, "altro": v}
            ag = Agente(cfg, imp, cliente, Arbitro(False, 0), log=lambda *_: None)
            for g in range(GIRI):
                lav = Lavoro(f"M{g}", TIPO, COMPITO)
                lav.inizio = time.time()
                msgs = storia(cfg, messaggio)
                rip = Ripetizioni(10 ** 6)        # solo per contare, non ferma
                t0 = time.monotonic()
                out = ag.passata(lav, msgs, tools=strumenti)
                s = time.monotonic() - t0
                rip.aggiungi(str(out.get("thinking") or "") + "\n" + str(out.get("content") or "")
                             + "\n")
                frase, volte = max(rip.conti.items(), key=lambda x: x[1], default=("", 0))
                r = {"messaggio": messaggio, "pp": v, "giro": g,
                     "a_vuoto": bool(out.get("giro_a_vuoto")), "token": lav.token,
                     "ragionamento": lav.ragionamento, "s": round(s, 1),
                     "scelta": "fermata" if out.get("giro_a_vuoto") else al_punto(
                         out.get("tool_calls")),
                     "ripetuta": volte, "frase": frase[:80]}
                righe.append(r)
                print(json.dumps(r, ensure_ascii=False), flush=True)
    print("\nmessaggio  pp    passate  a vuoto  mirata/legge  riscrive  token (mediana)  "
          "ragion.  s (mediana)  ripetizione max")
    for messaggio in MESSAGGI:
        for v in VALORI:
            rr = [r for r in righe if r["messaggio"] == messaggio and r["pp"] == v]
            if not rr:
                continue
            mir = sum(r["scelta"] == "mirata" or r["scelta"].startswith("legge") for r in rr)
            ris = sum(r["scelta"].startswith("riscrive") for r in rr)
            print(f"{messaggio:9}  {v:<4}  {len(rr):7}  {sum(r['a_vuoto'] for r in rr):7}  "
                  f"{mir:12}  {ris:8}  {statistics.median(r['token'] for r in rr):15.0f}  "
                  f"{statistics.median(r['ragionamento'] for r in rr):7.0f}  "
                  f"{statistics.median(r['s'] for r in rr):11.1f}  "
                  f"{max(r['ripetuta'] for r in rr):15}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
