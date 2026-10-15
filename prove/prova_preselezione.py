import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della preselezione dei tool System 1 (15/10, calliope/system1/preselezione.py,
in ombra; progetto docs/ricerche/2026-10-15-preselezione-tool.md).

- prototipi dagli schemi (nome, prima frase, esempi tra «…»), codifica «parole»;
- il banco (prove/banco_preselezione.py, 148 frasi con i tool veri di un registro completo):
  richiamo 100 % con il margine di serie, almeno un terzo delle frasi a «nucleo», e i
  contrari (con margine 0 il richiamo cade: il margine serve), tempi del decisore;
- i segnali di struttura: tool recente fuori dal nucleo, tool nominato nei dati del turno o
  nella proposta, foto → «tutti»; un nucleo con tool che non ci sono;
- `OmbraPreselezione` con un Brain finto: la scelta nel registro (`preselezione`: insieme,
  perché, schemi, mancati, variante dei più vicini), niente testo; decisore guasto → «errore»
  e niente eccezioni; spenta → nessun servizio; ciò che va al modello non cambia;
- configurazione (modo, codifica, margine, calliope.yaml), il ciclo (prima della risposta e
  nel registro), riassunto e riga di `calliope stato --turni`.
"""

import json
import time
from pathlib import Path
from types import SimpleNamespace

from calliope.config import Config
from calliope.system1 import preselezione as ps
from prove.banco_preselezione import CASI

RADICE = Path(__file__).resolve().parent.parent
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    if not ok:
        errori += 1
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


def registro():
    from prove.prova_politica import registro_completo
    return registro_completo()


def banco(p, margine):
    p.margine = margine
    presi = nucleo = 0
    mancati, ms = [], []
    for frase, acc, prima, rec in CASI:
        s = p.decide(ps.Richiesta(testo=frase, prima=prima, recenti=rec))
        ms.append(s.ms)
        if s.scelta == ps.NUCLEO_SCELTA:
            nucleo += 1
        if ps.preso(s, acc):
            presi += 1
        else:
            mancati.append((frase, acc[0]))
    ms.sort()
    return presi, nucleo, mancati, ms[len(ms) // 2], ms[int(.9 * len(ms))]


def prova_prototipi():
    schemas = [{"type": "function", "function": {
        "name": "lista_leggi", "description": "Legge una lista della casa: «cosa c'è nella "
        "lista della spesa?». Nella risposta usa la conferma.", "parameters": {}}}]
    pp = ps.prototipi(schemas)
    verifica("prototipi: nome e prima frase", pp[0] == ("lista_leggi", "lista leggi. Legge una "
             "lista della casa:"), str(pp[0]))
    verifica("prototipi: l'esempio tra «…»", ("lista_leggi", "cosa c'è nella lista della spesa?")
             in pp, str(pp))
    c = ps.CodificaParole()
    c.adatta(["accendi la luce", "che ore sono"])
    a, b, z = c.vettori(["Accendi la luce!", "accendi la luce", "che ore sono"])
    verifica("parole: maiuscole e punteggiatura non contano", abs(c.simile(a, b) - 1) < 1e-6)
    verifica("parole: frasi diverse lontane", c.simile(a, z) < 0.2, f"{c.simile(a, z):.2f}")


def prova_banco():
    reg = registro()
    p = ps.Preselettore()
    p.aggiorna(reg.all_schemas())
    n = len(CASI)
    verifica(f"banco: {n} frasi, tutti i {len(reg._tools)} tool del registro completo coperti",
             {t for c in CASI for t in c[1]} == set(reg._tools),
             str(set(reg._tools) - {t for c in CASI for t in c[1]}))
    verifica("banco: il nucleo di serie c'è tutto nel registro completo",
             p.nucleo == frozenset(ps.NUCLEO), str(set(ps.NUCLEO) - p.nucleo))
    presi, nucleo, mancati, p50, p90 = banco(p, ps.MARGINE)
    print(f"    margine {ps.MARGINE}: presi {presi}/{n}, «nucleo» {nucleo}/{n} "
          f"({len(p.nucleo)} schemi su {len(reg._tools)}), decisore p50 {p50} ms, p90 {p90} ms")
    verifica("banco: richiamo 100 % con il margine di serie", presi == n, str(mancati))
    verifica("banco: almeno 40 frasi su 148 a «nucleo»", nucleo >= 40, str(nucleo))
    verifica("banco: il decisore sta sotto i 30 ms (p90)", p90 < 30, f"{p90} ms")
    presi0, nucleo0, mancati0, *_ = banco(p, 0.0)
    verifica("banco, contrario: con margine 0 qualche tool si perde (il margine serve)",
             presi0 < n and nucleo0 > nucleo, f"{presi0}/{n} {mancati0[:3]}")
    p.margine = ps.MARGINE
    # Le chiacchiere e i tool di tutti i giorni vanno al nucleo, i tool rari a «tutti»
    for frase, atteso in (("Che ore sono?", ps.NUCLEO_SCELTA),
                          ("Aggiungi uova e farina alla spesa", ps.NUCLEO_SCELTA),
                          ("Blocca il computer", ps.TUTTI),
                          ("Fai una fattura a Rossi Impianti per trecento euro", ps.TUTTI)):
        s = p.decide(ps.Richiesta(frase))
        verifica(f"banco: «{frase}» → {atteso}", s.scelta == atteso,
                 f"{s.scelta} {s.perche} n={s.nucleo_max} f={s.fuori_max} {s.fuori_tool}")


def prova_struttura():
    reg = registro()
    p = ps.Preselettore()
    p.aggiorna(reg.all_schemas())
    base = p.decide(ps.Richiesta("Che ore sono?"))
    verifica("struttura: «Che ore sono?» da solo è nucleo", base.scelta == ps.NUCLEO_SCELTA
             and base.schemi == len(ps.NUCLEO) and base.schemi_tutti == len(reg._tools),
             f"{base.scelta} {base.schemi}/{base.schemi_tutti}")
    for nome, r, perche in (
            ("tool recente fuori dal nucleo",
             ps.Richiesta("Che ore sono?", recenti=("pc_volume",)), "tool_recente"),
            ("tool nei dati del turno", ps.Richiesta("Che ore sono?",
                                                       nominati=("sviluppo_passo",)),
             "tool_nei_dati"),
            ("foto con la frase", ps.Richiesta("Che ore sono?", foto=True), "foto_o_file")):
        s = p.decide(r)
        verifica(f"struttura: {nome} → tutti", s.scelta == ps.TUTTI and s.perche == perche
                 and s.nomi == frozenset(reg._tools), f"{s.scelta} {s.perche}")
    s = p.decide(ps.Richiesta("Che ore sono?", recenti=("ora_attuale", "lista_leggi")))
    verifica("struttura, contrario: tool recenti del nucleo non cambiano niente",
             s.scelta == ps.NUCLEO_SCELTA, s.perche)
    s = p.decide(ps.Richiesta("Che ore sono?", recenti=("tool_che_non_esiste",)))
    verifica("struttura, contrario: un nome che non c'è non conta", s.scelta == ps.NUCLEO_SCELTA)
    verifica("nominati: solo nomi interi", ps.nominati(
        ["Stato: sviluppo_passo aperto", "pc_volumex"], ["sviluppo_passo", "pc_volume"])
             == ("sviluppo_passo",))
    hist = [{"role": "user", "content": "Alza il volume"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"name": "pc_volume", "arguments": {}}]},
            {"role": "tool", "name": "pc_volume", "content": "{}"},
            {"role": "assistant", "content": "Fatto."},
            {"role": "user", "content": "[Dati del turno: ora 10:00]"}]
    verifica("tool recenti dalla storia di Brain", ps.tool_recenti(hist) == ("pc_volume",))
    verifica("la frase di prima salta i dati del turno",
             ps._ultima_domanda(hist) == "Alza il volume")
    # Un nucleo con tool che l'installazione non ha: si ignorano
    p2 = ps.Preselettore(nucleo=("ora_attuale", "inesistente"))
    p2.aggiorna(reg.all_schemas())
    verifica("nucleo: i tool che non ci sono si ignorano", p2.nucleo == {"ora_attuale"})
    # Senza indice: tutti
    s = ps.Preselettore().decide(ps.Richiesta("Che ore sono?"))
    verifica("senza indice → tutti", s.scelta == ps.TUTTI and s.perche == "senza_indice")
    # Lo stesso elenco non ricostruisce l'indice; un elenco nuovo sì
    verifica("aggiorna: stesso elenco, niente da rifare", p.aggiorna(reg.all_schemas()) is False)
    verifica("aggiorna: un tool in meno, indice rifatto",
             p.aggiorna(reg.all_schemas()[1:]) is True)


class BrainFinto:
    def __init__(self, schemas, history=None, pending=None):
        self._s = schemas
        self.history = history or []
        self.pending = pending
        self.chiamate = 0

    def schemi(self):
        self.chiamate += 1
        return self._s


def prova_ombra():
    reg = registro()
    cfg = Config()
    cfg.preselezione_tool = "ombra"
    o = ps.load_preselezione(cfg, log=lambda *_: None)
    verifica("ombra: il servizio parte con preselezione_tool: ombra", o is not None)
    brain = BrainFinto(reg.all_schemas())
    # La prima volta il thread del decisore nasce e l'indice si costruisce (dentro il thread)
    o.chiudi({}, o.valuta(brain, "Buongiorno", None), attesa_s=5)
    t0 = time.perf_counter()
    fut = o.valuta(brain, "Che ore sono?", None)
    costo = (time.perf_counter() - t0) * 1000
    verifica("ombra: valuta non aspetta il decisore (< 2 ms nel thread del ciclo)",
             fut is not None and costo < 2, f"{costo:.2f} ms")
    rec = {"tool": [{"nome": "ora_attuale", "ok": True}], "testo": "Che ore sono?"}
    o.chiudi(rec, fut, attesa_s=5)
    p = rec.get("preselezione") or {}
    verifica("ombra: nel registro insieme, schemi e niente mancati",
             p.get("insieme") == "nucleo" and p.get("schemi") == len(ps.NUCLEO)
             and p.get("schemi_tutti") == len(reg._tools) and p.get("mancati") == []
             and p.get("codifica") == "parole", str(p))
    verifica("ombra: solo nomi e numeri, niente testo della frase",
             "Che ore" not in json.dumps(p, ensure_ascii=False))
    # Un tool usato fuori dal nucleo con la scelta «nucleo»: mancato
    fut = o.valuta(brain, "Che ore sono?", None)
    rec = {"tool": [{"nome": "pc_blocca", "ok": True}, {"nome": "inventato", "sconosciuto": True}]}
    o.chiudi(rec, fut, attesa_s=5)
    p = rec["preselezione"]
    verifica("ombra: il tool usato fuori dall'insieme è un mancato (lo sconosciuto no)",
             p["mancati"] == ["pc_blocca"] and "pc_blocca" in p["mancati_top"], str(p))
    # La storia del Brain: il tool recente fuori dal nucleo porta a «tutti»
    brain2 = BrainFinto(reg.all_schemas(), history=[
        {"role": "user", "content": "Alza il volume"},
        {"role": "assistant", "content": "", "tool_calls": [{"name": "pc_volume",
                                                               "arguments": {}}]}])
    rec = {"tool": [{"nome": "pc_volume", "ok": True}]}
    o.chiudi(rec, o.valuta(brain2, "Più forte", None), attesa_s=5)
    verifica("ombra: «Più forte» dopo pc_volume → tutti, niente mancati",
             rec["preselezione"]["insieme"] == "tutti"
             and rec["preselezione"]["perche"] == "tool_recente"
             and rec["preselezione"]["mancati"] == [], str(rec["preselezione"]))
    # La proposta aperta con un tool fuori dal nucleo
    brain3 = BrainFinto(reg.all_schemas(), pending={"tool": "installa_avvia"})
    rec = {}
    o.chiudi(rec, o.valuta(brain3, "Sì, vai", None), attesa_s=5)
    verifica("ombra: la proposta aperta nomina un tool fuori dal nucleo → tutti",
             rec["preselezione"]["perche"] == "tool_nei_dati", str(rec["preselezione"]))
    # Il modello vede sempre tutti gli schemi: valuta non tocca il Brain
    verifica("ombra: gli schemi del Brain non cambiano", len(brain.schemi()) == len(reg._tools))
    # Frase vuota: niente
    verifica("ombra: frase vuota → niente", o.valuta(brain, "  ", None) is None)
    # Decisore guasto: «errore» nel registro, nessuna eccezione
    class Rotto:
        def schemi(self):
            raise RuntimeError("guasto")
        history = []
        pending = None
    rec = {}
    o.chiudi(rec, o.valuta(Rotto(), "Che ore sono?", None), attesa_s=5)
    verifica("ombra: decisore guasto → «errore» nel registro, nessuna eccezione",
             rec.get("preselezione", {}).get("esito") == "errore", str(rec))
    # Lento: «in_ritardo»
    class Lento:
        nome, scelte = "lento", ("nucleo", "tutti")

        def decide(self, dati):
            time.sleep(0.3)
            raise RuntimeError("tardi")
    o2 = ps.OmbraPreselezione(cfg, log=lambda *_: None)
    o2.decisore.decisore = Lento()
    rec = {}
    o2.chiudi(rec, o2.valuta(brain, "Che ore sono?", None), attesa_s=0.01)
    verifica("ombra: decisore lento → «in_ritardo»",
             rec.get("preselezione") == {"esito": "in_ritardo"}, str(rec))
    o.ferma()
    o2.ferma()
    cfg.preselezione_tool = "spenta"
    verifica("spenta: nessun servizio", ps.load_preselezione(cfg, log=lambda *_: None) is None)
    cfg.preselezione_tool = "boh"
    verifica("modo sconosciuto: spenta", ps.modo(cfg) == "spenta")


def prova_config_e_ciclo():
    c = Config()
    verifica("config: di serie spenta, parole, margine 0,10",
             c.preselezione_tool == "spenta" and c.preselezione_codifica == "parole"
             and abs(c.preselezione_margine - ps.MARGINE) < 1e-9)
    from calliope import config as cm
    verifica("config: modo validato", cm.VALIDATORI["preselezione_tool"](" Ombra ") == "ombra")
    try:
        cm.VALIDATORI["preselezione_tool"]("attiva")
        ok = False
    except ValueError:
        ok = True
    verifica("config, contrario: «attiva» non c'è ancora", ok)
    verifica("config: margine con un intervallo", cm.fuori_limiti("preselezione_margine", 3.0)
             is not None and cm.fuori_limiti("preselezione_margine", 0.1) is None)
    yaml = (RADICE / "calliope.yaml").read_text(encoding="utf-8")
    verifica("calliope.yaml: i campi della preselezione",
             "preselezione_tool: spenta" in yaml and "preselezione_margine:" in yaml)
    src = (RADICE / "calliope" / "ciclo.py").read_text(encoding="utf-8")
    i_val = src.find("pre.valuta(brain, t.text")
    i_stream = src.find("frasi = split_sentences(brain.stream_reply(")
    i_tool = src.find("tool=tools_per_registro(getattr(brain, \"last_tools\", None)))")
    i_chiudi = src.find("pre.chiudi(rec, job)")
    verifica("ciclo: il decisore parte prima della risposta e chiude dopo i tool del turno",
             0 < i_val < i_stream and 0 < i_tool < i_chiudi, f"{i_val} {i_stream} {i_tool} "
             f"{i_chiudi}")
    src = (RADICE / "calliope" / "main.py").read_text(encoding="utf-8")
    verifica("main: il servizio dell'ombra", "s.preselezione = load_preselezione(cfg)" in src)


def prova_riassunto():
    turni = [
        {"esito": "risposta", "tool": [{"nome": "ora_attuale"}],
         "preselezione": {"insieme": "nucleo", "schemi": 28, "schemi_tutti": 85, "ms": 2.0,
                          "mancati": [], "mancati_top": []}},
        {"esito": "risposta", "tool": [{"nome": "pc_blocca"}],
         "preselezione": {"insieme": "nucleo", "schemi": 28, "schemi_tutti": 85, "ms": 3.0,
                          "mancati": ["pc_blocca"], "mancati_top": []}},
        {"esito": "risposta", "tool": [],
         "preselezione": {"insieme": "tutti", "schemi": 85, "schemi_tutti": 85, "ms": 4.0,
                          "mancati": [], "mancati_top": []}},
        {"esito": "risposta", "preselezione": {"esito": "in_ritardo"}},
        {"esito": "risposta", "tool": [{"nome": "ora_attuale"}]},
    ]
    r = ps.riassunto(turni)
    verifica("riassunto: risposte, nucleo, richiamo, variante, risparmio, cambi",
             r["risposte"] == 3 and r["nucleo"] == 2 and r["con_tool"] == 2
             and r["richiamo"] == 0.5 and r["richiamo_top"] == 1.0
             and r["risparmio_medio"] == 38.0 and r["cambi"] == 1
             and r["mancati"] == [("pc_blocca", 1)], str(r))
    t = ps.testo(r)
    verifica("riga di calliope stato", "«nucleo» in 2" in t and "50.0 %" in t
             and "pc_blocca ×1" in t, t)
    verifica("riga senza misure", "nessuna risposta" in ps.testo(ps.riassunto([])))
    molti = [turni[1]] * 25
    verifica("avviso sotto il 99 % con almeno 20 turni con tool",
             "ATTENZIONE" in ps.testo(ps.riassunto(molti)))
    verifica("contrario: nessun avviso col richiamo pieno",
             "ATTENZIONE" not in ps.testo(ps.riassunto([turni[0]] * 25)))
    src = (RADICE / "calliope" / "stato.py").read_text(encoding="utf-8")
    verifica("calliope stato --turni: sezione e JSON",
             "preselezione_s1.testo(presel)" in src and '"preselezione": presel' in src)


if __name__ == "__main__":
    prova_prototipi()
    prova_banco()
    prova_struttura()
    prova_ombra()
    prova_config_e_ciclo()
    prova_riassunto()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    sys.exit(1 if errori else 0)
