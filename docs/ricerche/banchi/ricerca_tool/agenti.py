"""
Agenti come tool e lavori in secondo piano con un solo modello residente (26/09/2026).

Parte 1 — «casa»: 26 entità finte in stile Home Assistant. Tre modi:
  diretto  Calliope vede casa_comando/casa_stato con l'elenco delle entità nella descrizione;
  agente   Calliope vede chiedi_alla_casa(richiesta); l'agente (stesso modello, prompt,
           tool e storia propri) esegue e restituisce una frase; Calliope poi risponde;
  agente+  come agente, ma Calliope dice subito una frase fissa e la frase dell'agente va
           dritta al TTS (niente seconda passata di Calliope).
Parte 2 — contesa della GPU: la prima frase della voce mentre un agente in secondo
  piano genera (coda FIFO di Ollama), e con un «arbitro» che chiude lo stream in secondo
  piano quando arriva la voce.

Uso: .venv\\Scripts\\python.exe -u docs\\ricerche\\banchi\\ricerca_tool\\agenti.py [casa|contesa|tutto] [modello]
"""

import json
import os
import statistics
import sys
import threading
import time

import httpx

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.abspath(os.path.join(QUI, "..", "..", "..", "..")))   # radice del repository

import catalogo as K                                           # noqa: E402
from banco import HTTP, URL, SYSTEM, corpo, turno, risultato_finto, TUTTI_SCHEMI   # noqa: E402

MODEL = sys.argv[2] if len(sys.argv) > 2 else "gemma4:e4b-it-qat"
QUALE = sys.argv[1] if len(sys.argv) > 1 else "tutto"

# ─────────────────────────────── ENTITÀ ───────────────────────────────
ENTITA = [
    ("light.soggiorno_lampadario", "lampadario", "soggiorno", "spenta"),
    ("light.soggiorno_piantana", "piantana", "soggiorno", "accesa"),
    ("light.cucina", "luce della cucina", "cucina", "spenta"),
    ("light.cucina_sottopensile", "sottopensile", "cucina", "accesa"),
    ("light.camera", "luce della camera", "camera", "spenta"),
    ("light.camera_comodino_dario", "comodino di Dario", "camera", "spenta"),
    ("light.camera_comodino_giulia", "comodino di Giulia", "camera", "spenta"),
    ("light.cameretta", "luce della cameretta", "cameretta", "spenta"),
    ("light.bagno", "luce del bagno", "bagno", "spenta"),
    ("light.studio", "luce dello studio", "studio", "accesa"),
    ("light.corridoio", "luce del corridoio", "corridoio", "spenta"),
    ("cover.soggiorno", "tapparella del soggiorno", "soggiorno", "aperta"),
    ("cover.cucina", "tapparella della cucina", "cucina", "aperta"),
    ("cover.camera", "tapparella della camera", "camera", "chiusa"),
    ("cover.cameretta", "tapparella della cameretta", "cameretta", "aperta"),
    ("climate.casa", "riscaldamento", "casa", "20 gradi"),
    ("sensor.temperatura_soggiorno", "temperatura del soggiorno", "soggiorno", "21,0 °C"),
    ("sensor.temperatura_camera", "temperatura della camera", "camera", "19,5 °C"),
    ("sensor.temperatura_bagno", "temperatura del bagno", "bagno", "22,5 °C"),
    ("binary_sensor.porta_ingresso", "porta d'ingresso", "ingresso", "chiusa"),
    ("binary_sensor.finestra_bagno", "finestra del bagno", "bagno", "aperta"),
    ("binary_sensor.finestra_cucina", "finestra della cucina", "cucina", "chiusa"),
    ("switch.lavatrice", "lavatrice", "bagno", "spenta"),
    ("switch.macchina_caffe", "macchina del caffè", "cucina", "spenta"),
    ("fan.camera", "ventilatore", "camera", "spento"),
    ("media_player.soggiorno", "cassa del soggiorno", "soggiorno", "in pausa"),
]
IDS = [e[0] for e in ENTITA]
ELENCO = "\n".join(f"- {i}: {n} ({a}), ora {s}" for i, n, a, s in ENTITA)
ELENCO_BREVE = "; ".join(f"{i} = {n} ({a})" for i, n, a, _ in ENTITA)

CASA_COMANDO = {"type": "function", "function": {
    "name": "casa_comando", "description": "Comanda un dispositivo di casa.",
    "parameters": {"type": "object", "properties": {
        "entita": {"type": "string", "enum": IDS},
        "azione": {"type": "string", "enum": ["accendi", "spegni", "apri", "chiudi", "imposta"]},
        "valore": {"type": "number", "description": "per imposta: percentuale o gradi"}},
        "required": ["entita", "azione"]}}}
CASA_STATO = {"type": "function", "function": {
    "name": "casa_stato", "description": "Legge lo stato di un dispositivo o sensore di casa.",
    "parameters": {"type": "object", "properties": {"entita": {"type": "string", "enum": IDS}},
                   "required": ["entita"]}}}
# Variante «diretta»: Calliope vede le entità nella descrizione (come fa Home Assistant)
DIR_COMANDO = json.loads(json.dumps(CASA_COMANDO))
DIR_COMANDO["function"]["description"] = "Comanda un dispositivo di casa. Dispositivi: " + ELENCO_BREVE + "."
DIR_STATO = json.loads(json.dumps(CASA_STATO))
DIR_STATO["function"]["description"] = ("Legge lo stato di un dispositivo o sensore di casa "
                                        "(vedi l'elenco in casa_comando).")
CHIEDI = {"type": "function", "function": {
    "name": "chiedi_alla_casa",
    "description": ("Affida all'agente della casa qualunque richiesta su luci, tapparelle, "
                    "riscaldamento, prese, elettrodomestici, ventilatori, sensori, porte e finestre: "
                    "conosce tutti i dispositivi. Passagli la richiesta completa."),
    "parameters": {"type": "object", "properties": {"richiesta": {"type": "string"}},
                   "required": ["richiesta"]}}}

AGENTE_SYS = ("Sei l'agente della casa di Calliope, un'assistente vocale. Esegui la richiesta con "
              "casa_comando e casa_stato, usando solo le entità dell'elenco; se la richiesta "
              "riguarda più dispositivi, chiamali tutti. Poi rispondi con UNA frase breve in "
              "italiano, da leggere a voce, che dice cosa hai fatto o letto. Se non si può fare, "
              "dillo. Dispositivi di casa:\n" + ELENCO)

CASA_RICHIESTE = [
    ("Accendi la piantana in soggiorno", [("light.soggiorno_piantana", "accendi")]),
    ("Spegni il sottopensile della cucina", [("light.cucina_sottopensile", "spegni")]),
    ("Chiudi tutte le tapparelle", [("cover.soggiorno", "chiudi"), ("cover.cucina", "chiudi"),
                                    ("cover.camera", "chiudi"), ("cover.cameretta", "chiudi")]),
    ("Accendi la macchina del caffè", [("switch.macchina_caffe", "accendi")]),
    ("Che temperatura c'è in camera?", [("sensor.temperatura_camera", "stato")]),
    ("La finestra del bagno è aperta?", [("binary_sensor.finestra_bagno", "stato")]),
    ("Accendi il ventilatore in camera", [("fan.camera", "accendi")]),
    ("Spegni tutte le luci del soggiorno", [("light.soggiorno_lampadario", "spegni"),
                                            ("light.soggiorno_piantana", "spegni")]),
    ("Porta a metà la tapparella della cameretta", [("cover.cameretta", "imposta")]),
    ("La lavatrice è accesa?", [("switch.lavatrice", "stato")]),
    ("Metti il riscaldamento a 20 gradi", [("climate.casa", "imposta")]),
    ("Accendi la luce del comodino di Dario", [("light.camera_comodino_dario", "accendi")]),
]


def esegui_casa(nome, args):
    if nome == "casa_stato":
        e = next((x for x in ENTITA if x[0] == args.get("entita")), None)
        return json.dumps({"entita": args.get("entita"), "stato": e[3] if e else "sconosciuta"},
                          ensure_ascii=False)
    if nome == "casa_comando":
        if args.get("entita") not in IDS:
            return json.dumps({"errore": "entità sconosciuta"})
        return json.dumps({"ok": True, **args}, ensure_ascii=False)
    return risultato_finto(nome, args)


def coppie(calls):
    out = set()
    for c in calls:
        a = c["arguments"]
        if c["name"] == "casa_comando":
            out.add((a.get("entita"), a.get("azione")))
        elif c["name"] == "casa_stato":
            out.add((a.get("entita"), "stato"))
    return out


def ciclo(messages, tools, esegui, max_giri=4):
    """Ciclo di tool calling: → (testo finale, chiamate, n passate, t primo testo, t_prima_decisione)"""
    t0 = time.perf_counter()
    calls_all, passate, t_testo, t_dec = [], 0, None, None
    testo = ""
    for giro in range(max_giri + 1):
        ts = time.perf_counter()
        r = turno(MODEL, messages, tools if giro < max_giri else None,
                  TUTTI_SCHEMI + [CASA_COMANDO, CASA_STATO, CHIEDI])
        passate += 1
        if t_dec is None:
            t_dec = ts - t0 + (r["t_evento"] or r["t_tot"])
        if r["t_testo"] is not None and t_testo is None:
            t_testo = ts - t0 + r["t_testo"]
        testo = r["testo"]
        if not r["calls"]:
            break
        messages = messages + [{"role": "assistant", "content": r["testo"], "tool_calls": r["calls"]}]
        for c in r["calls"]:
            calls_all.append(c)
            messages.append({"role": "tool", "name": c["name"], "content": esegui(c["name"], c["arguments"])})
    return testo, calls_all, passate, t_testo, t_dec


def parte_casa():
    nucleo = K.schemas(K.NUCLEO)
    righe = []
    for frase, attese in CASA_RICHIESTE:
        for modo in ("diretto", "agente"):
            t0 = time.perf_counter()
            sub = {}

            def esegui(nome, args):
                if nome == "chiedi_alla_casa":
                    ts = time.perf_counter()
                    msgs = [{"role": "system", "content": AGENTE_SYS},
                            {"role": "user", "content": str(args.get("richiesta") or frase)}]
                    testo, calls, passate, t_testo_ag, _ = ciclo(msgs, [CASA_COMANDO, CASA_STATO], esegui_casa)
                    sub.update({"calls": calls, "passate": passate, "testo": testo,
                                "t_inizio": ts - t0, "t_fine": time.perf_counter() - t0,
                                # la frase dell'agente comincia ad arrivare all'ultima passata:
                                "t_testo": (ts - t0 + t_testo_ag) if t_testo_ag else None})
                    return json.dumps({"esito": testo}, ensure_ascii=False)
                return esegui_casa(nome, args)

            tools = nucleo + ([DIR_COMANDO, DIR_STATO] if modo == "diretto" else [CHIEDI])
            msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": frase}]
            testo, calls, passate, t_testo, t_dec = ciclo(msgs, tools, esegui)
            fatte = coppie(sub.get("calls", []) if modo == "agente" else calls)
            ok = set(attese) <= fatte
            riga = {"frase": frase, "modo": modo, "ok": ok, "fatte": sorted(map(list, fatte)),
                    "delegato": any(c["name"] == "chiedi_alla_casa" for c in calls),
                    "passate": passate + sub.get("passate", 0), "t_decisione": round(t_dec, 3),
                    "t_testo": round(t_testo, 3) if t_testo else None,
                    "t_tot": round(time.perf_counter() - t0, 3), "detto": testo}
            if modo == "agente":
                # agente+: frase fissa subito alla delega, poi la frase dell'agente dritta al TTS
                riga["t_frase_fissa"] = round(t_dec, 3) if riga["delegato"] else None
                riga["t_testo_agente"] = round(sub["t_testo"], 3) if sub.get("t_testo") else None
                riga["detto_agente"] = sub.get("testo")
            righe.append(riga)
            print(f"{'ok ' if ok else 'NO '} {modo:8} dec {t_dec:4.2f}s testo {riga['t_testo'] or 0:4.2f}s "
                  f"tot {riga['t_tot']:4.2f}s pass {riga['passate']} "
                  f"{('agente→testo %.2fs' % riga['t_testo_agente']) if riga.get('t_testo_agente') else ''} "
                  f"«{frase}» {riga['fatte']} | {testo[:70]!r}", flush=True)
    with open(os.path.join(QUI, "risultati", f"agenti_casa_{MODEL.replace(':', '_')}.jsonl"), "w",
              encoding="utf-8") as f:
        for r in righe:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for modo in ("diretto", "agente"):
        rr = [r for r in righe if r["modo"] == modo]
        med = lambda k: statistics.median([r[k] for r in rr if r.get(k) is not None] or [0])
        print(f"### {modo}: giusti {sum(r['ok'] for r in rr)}/{len(rr)}, decisione {med('t_decisione'):.2f}s, "
              f"primo testo {med('t_testo'):.2f}s, totale {med('t_tot'):.2f}s, passate {med('passate')}"
              + (f", frase fissa {med('t_frase_fissa'):.2f}s, testo agente {med('t_testo_agente'):.2f}s"
                 if modo == "agente" else ""))


# ─────────────────────────────── CONTESA ───────────────────────────────
DOC = ("Il mercato comunale apre alle sette. " * 400)[:18000]


class Sfondo(threading.Thread):
    """Un agente in secondo piano che genera a lungo (o legge un documento lungo)."""

    def __init__(self, lungo_prompt=False):
        super().__init__(daemon=True)
        self.stop = threading.Event()
        self.token = 0
        self.t_primo = self.t_fine = None
        self.lungo = lungo_prompt
        self.stats = {}

    def run(self):
        http = httpx.Client(base_url=URL, timeout=300)
        if self.lungo:
            msgs = [{"role": "system", "content": "Sei un agente che riassume documenti."},
                    {"role": "user", "content": "Riassumi in dieci frasi questo documento:\n" + DOC}]
        else:
            msgs = [{"role": "system", "content": "Sei un agente ricercatore che scrive relazioni."},
                    {"role": "user", "content": "Scrivi una relazione dettagliata di almeno 600 parole "
                                                "sulla storia di Venezia."}]
        t0 = time.perf_counter()
        with http.stream("POST", "/api/chat", json=corpo(MODEL, msgs, num_predict=900)) as r:
            for line in r.iter_lines():
                if self.stop.is_set():
                    break                                  # chiude la connessione
                if not line:
                    continue
                obj = json.loads(line)
                if (obj.get("message") or {}).get("content"):
                    self.token += 1
                    if self.t_primo is None:
                        self.t_primo = time.perf_counter() - t0
                if obj.get("done"):
                    self.stats = {k: obj.get(k) for k in ("prompt_eval_count", "prompt_eval_duration", "eval_count")}
                    break
        self.t_fine = time.perf_counter() - t0


def voce():
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "Che ore sono?"}]
    t0 = time.perf_counter()
    r = turno(MODEL, msgs, K.schemas(K.S10), TUTTI_SCHEMI)
    msgs += [{"role": "assistant", "content": "", "tool_calls": r["calls"]}] + \
            [{"role": "tool", "name": c["name"], "content": risultato_finto(c["name"], c["arguments"])}
             for c in r["calls"]]
    t1 = time.perf_counter()
    r2 = turno(MODEL, msgs, K.schemas(K.S10), TUTTI_SCHEMI) if r["calls"] else r
    base = (t1 - t0) if r["calls"] else 0
    return {"t_decisione": round(r["t_evento"] or r["t_tot"], 3),
            "t_testo": round(base + (r2["t_testo"] or r2["t_tot"]), 3)}


def parte_contesa():
    righe = []
    voce()
    for rip in range(3):
        righe.append({"scenario": "voce da sola", **voce()})
        for lungo in (False, True):
            nome = "prompt lungo (18k caratteri)" if lungo else "generazione lunga"
            # 1) FIFO: la voce aspetta
            s = Sfondo(lungo)
            s.start()
            time.sleep(1.5 if not lungo else 0.3)
            tv = time.perf_counter()
            v = voce()
            s.join()
            righe.append({"scenario": f"{nome}: voce in coda", **v,
                          "sfondo_token": s.token, "sfondo_fine": round(s.t_fine, 2),
                          "sfondo_prompt_ms": round((s.stats.get("prompt_eval_duration") or 0) / 1e6)})
            # 2) arbitro: chiude lo stream in secondo piano, poi la voce
            s = Sfondo(lungo)
            s.start()
            time.sleep(1.5 if not lungo else 0.3)
            s.stop.set()
            tc = time.perf_counter()
            v = voce()
            s.join(timeout=60)
            righe.append({"scenario": f"{nome}: arbitro (chiude lo sfondo)", **v,
                          "sfondo_token": s.token})
            # 3) ripresa del lavoro in secondo piano dopo la voce: quanto costa rileggere il prompt
            s = Sfondo(lungo)
            s.run()
            righe.append({"scenario": f"{nome}: ripresa dopo la voce",
                          "sfondo_primo_token": round(s.t_primo or 0, 2),
                          "sfondo_prompt_ms": round((s.stats.get("prompt_eval_duration") or 0) / 1e6)})
        for r in righe[-7:]:
            print(json.dumps(r, ensure_ascii=False), flush=True)
    with open(os.path.join(QUI, "risultati", f"agenti_contesa_{MODEL.replace(':', '_')}.jsonl"), "w",
              encoding="utf-8") as f:
        for r in righe:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print()
    for sc in dict.fromkeys(r["scenario"] for r in righe):
        rr = [r for r in righe if r["scenario"] == sc]
        med = lambda k: statistics.median([r[k] for r in rr if r.get(k) is not None] or [0])
        print(f"### {sc}: decisione {med('t_decisione'):.2f}s, primo testo {med('t_testo'):.2f}s, "
              f"sfondo token {med('sfondo_token')}, sfondo primo token {med('sfondo_primo_token')}s, "
              f"sfondo prompt {med('sfondo_prompt_ms')} ms")


if __name__ == "__main__":
    HTTP.post("/api/chat", json=corpo(MODEL, [{"role": "user", "content": "ciao"}], stream=False,
                                      num_predict=1)).raise_for_status()
    if QUALE in ("casa", "tutto"):
        parte_casa()
    if QUALE in ("contesa", "tutto"):
        parte_contesa()
