"""
Prova a secco del pezzo «in attesa» e del tetto alla riapertura (14/10/2026 notte, dopo la seconda
prova vera in auto: prima frase mediana 2,31 s contro ~1,2–1,3 s dei giorni prima, rilettura 0,86 s,
token riletti p50 1965 e p90 4147; fino a 3709 caratteri di righe nuove fra un turno e l'altro e
36 righe, 5476 caratteri, tutte insieme quando la conversazione si riapriva).

Un motore finto con la cache del prefisso come Ollama (una sola: la richiesta nuova rilegge i
messaggi dopo il primo diverso da quelli della richiesta di prima, riscaldamento compreso) e una
conversazione finta come quella dell'auto (righe fitte fra un turno e l'altro, due riaperture dopo
`storia_inattiva_s`), con l'orologio finto. Due modi sulla stessa conversazione:

- `prima`: `stanza_attesa: false` e la riapertura come prima (finestra di 8 minuti, tetto 6000);
- `dopo`: il pezzo in attesa (Brain.stanza_attesa_prepara ogni 5 s finti, poi
  stanza_attesa_scalda) e il primo pezzo di una conversazione col tetto
  `stanza_riapertura_caratteri`.

Si verifica: i token riletti al turno (quelli che pesano sulla prima frase) calano, quelli letti in
secondo piano no (si spostano), la richiesta del turno comincia con quella scaldata fino all'ultimo
pezzo in attesa (byte per byte), ogni riga una volta sola e nell'ordine, la domanda appena detta
mai in un pezzo in attesa (quiete di 4 s), niente pezzo in attesa durante una risposta, con la
conversazione in scadenza, in pausa per ospiti, con la stanza spenta o con `stanza_attesa: false`;
«dimentica» toglie anche i pezzi in attesa; la finestra della riapertura arriva all'inizio
dell'ultimo scambio (la risposta di nove minuti prima) e il tetto vale. Con `--misura` la tabella
per turno. Nomi di fantasia (Carlo amministra, Nicola ha 14 anni). ~2 s.
"""

import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope import provenienza as prov  # noqa: E402
from calliope.brain import Brain, _tokens  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.conversazione import Conversazione  # noqa: E402
from calliope.stanza import contesto as ctx_mod  # noqa: E402
from calliope.stanza.ascolto import Stanza  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio else ""),
          flush=True)


class STTFinto:
    def transcribe(self, audio, **k):
        return ""


class Prof:
    def __init__(self, pid, name, nascita=None):
        self.id, self.name, self.nascita = pid, name, nascita
        self.admin = name == "Carlo"
        self.tutori = []
        self.fascia = self.preferred_voice = self.tono = self.preferred_tone = None


class Voci:
    P = {"Carlo": Prof("carlo-id", "Carlo"), "Nicola": Prof("nicola-id", "Nicola", "2012-05-01")}

    def get(self, n):
        return self.P.get(n)

    def known_speakers(self):
        return list(self.P)


class Chi:
    current_speaker, current_level, identified_by = "Carlo", "amministra", "voce"
    compagnia = compagnia_sconosciute = False


def _chiave(m):
    return json.dumps({k: v for k, v in m.items() if not k.startswith("_")},
                      ensure_ascii=False, sort_keys=True)


class MotoreFinto:
    """La cache del prefisso di Ollama, a messaggi: una richiesta rilegge i messaggi dopo il
    primo diverso dalla richiesta di prima (riscaldamenti compresi)."""

    def __init__(self):
        self.cache: list[str] = []
        self.turni: list[int] = []        # token riletti dalla prima passata di ogni risposta
        self.sfondo: list[int] = []       # token letti dai riscaldamenti
        self.richieste: list[list[dict]] = []
        self.scaldate: list[list[dict]] = []

    def _leggi(self, messages) -> tuple[int, int]:
        chiavi = [_chiave(m) for m in messages]
        k = 0
        for a, b in zip(chiavi, self.cache):
            if a != b:
                break
            k += 1
        self.cache = chiavi
        return _tokens(messages), _tokens(messages[k:])

    def stream(self, messages, tools):
        self.richieste.append([dict(m) for m in messages])
        tot, riletti = self._leggi(messages)
        self.turni.append(riletti)
        yield ("text", "Va bene.")
        yield ("usage", {"prompt": tot, "in_cache": tot - riletti, "output": 3})

    def warmup(self, messages, tools):
        self.scaldate.append([dict(m) for m in messages])
        tot, letti = self._leggi(messages)
        self.sfondo.append(letti)
        return {"prompt": tot}


def cfg_base(**k) -> Config:
    c = Config()
    c.stanza = "ombra"
    c.stanza_contesto = True
    c.storia_inattiva_s = 300.0
    for a, v in k.items():
        setattr(c, a, v)
    return c


def nuova_stanza(cfg, sat=1, nome="auto"):
    st = Stanza(cfg, STTFinto(), registry=Voci(), log=lambda m: None)
    st._info[sat] = {"nome": nome, "stanza": nome, "canale": "satellite"}
    return st


def brain(cfg, st):
    from calliope.tools.builtin import build_registry
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = cfg, build_registry(), []
    b.conv = Conversazione("persona:carlo-id")
    b.tool_ctx = type("T", (), {"speaker_ctx": Chi(), "speakers": Voci(), "stanza": st})()
    b.backend = MotoreFinto()
    return b


def riga(st, sat, testo, inizio, nome=None, durata=4.0, chi=None, rivolta="ignoto"):
    return st.registro(sat).aggiungi(
        "riga", segmento=None, versione=1, inizio=round(inizio, 3),
        fine=round(inizio + durata, 3), testo=testo,
        chi=chi or (f"persona:{nome}" if nome else "ignoto"),
        nome=nome, sicurezza="voce" if nome else "nessuna", p_min=None, rivolta=rivolta,
        minore=nome == "Nicola").seq


CHIACCHIERE = [
    "Hai visto che domani danno pioggia su tutta la costa fino a sera?",
    "Sì, ma per la gita di sabato dicono che torna il sole, almeno al mattino.",
    "Allora partiamo presto e ci fermiamo a fare colazione al bar della piazza.",
    "Io però voglio portare la bici, l'ultima volta non c'era posto in macchina.",
    "La mettiamo sul portapacchi, basta ricordarsi le cinghie in garage.",
    "A proposito, nella chat della classe dicono che troppo aura vuol dire che è tanta roba.",
    "Ma chi ha inventato queste parole? Ogni settimana ne esce una nuova.",
    "Le inventano su internet, poi le dicono tutti per un mese e spariscono.",
    "Comunque la festa della cresima è il diciotto, la mamma ha già prenotato il ristorante.",
    "Il regalo lo prendiamo insieme, magari un orologio o una cosa per la musica.",
    "Ricordati che giovedì c'è l'allenamento spostato alle sei e mezza.",
    "Va bene, ma allora la cena la facciamo un po' più tardi del solito.",
]
# Righe nuove prima di ogni domanda e secondi dall'ultimo turno, come la prova in auto: due
# riaperture (oltre storia_inattiva_s), conversazione fitta in mezzo
COPIONE = [(15, 160), (0, 25), (24, 240), (1, 30), (0, 20), (10, 120), (0, 30),
           (36, 420), (0, 25), (9, 150), (32, 400), (1, 30), (0, 30), (4, 60)]
DOMANDE = ["Calliope, quando è Halloween?", "Calliope, e la festa quando è?",
           "Calliope, cosa vuol dire troppo aura?", "Calliope, che ore sono?",
           "Calliope, grazie, e domani piove?", "Calliope, cosa diceva Nicola della bici?",
           "Calliope, e il regalo?", "Calliope, a che ora è l'allenamento?",
           "Calliope, quanto fa sette per otto?", "Calliope, tu che ne pensi?",
           "Calliope, ti ricordi quando è la cresima?", "Calliope, e il ristorante?",
           "Calliope, va bene.", "Calliope, riassumimi la gita."]


def giro(dopo: bool, misura_prima: bool = False):
    """La conversazione dell'auto. Restituisce (brain, stanza, per turno)."""
    extra = {"stanza_attesa": dopo}
    if not dopo:
        extra["stanza_riapertura_caratteri"] = 6000
    cfg = cfg_base(**extra)
    st = nuova_stanza(cfg)
    b = brain(cfg, st)
    salva = ctx_mod.RIAPERTURA_MAX_S
    if not dopo:
        ctx_mod.RIAPERTURA_MAX_S = 0.0        # come prima: solo gli ultimi 8 minuti
    t = time.time() - sum(g for _, g in COPIONE) - 60
    k = 0
    out = []
    try:
        for n, (righe_n, gap) in enumerate(COPIONE):
            inizio_gap = t
            sfondo_prima = sum(b.backend.sfondo)
            scaldate_prima = len(b.backend.scaldate)
            passo = gap / (righe_n + 1)
            ultimo_tick = inizio_gap
            for j in range(righe_n):
                quando = inizio_gap + (j + 1) * passo - 4.0
                nome = ("Carlo", "Nicola", None)[k % 3]
                riga(st, 1, f"{CHIACCHIERE[k % len(CHIACCHIERE)]} ({n}.{j})", quando, nome)
                k += 1
                # Il thread delle righe in attesa, ogni 5 s finti
                while dopo and ultimo_tick + 5.0 <= quando + 4.0:
                    ultimo_tick += 5.0
                    b.last_turn_at = time.monotonic() - (ultimo_tick - inizio_gap)
                    if b.stanza_attesa_prepara(ora=ultimo_tick):
                        b.stanza_attesa_scalda()
            t = inizio_gap + gap
            while dopo and ultimo_tick + 5.0 <= t - 1.0:
                ultimo_tick += 5.0
                b.last_turn_at = time.monotonic() - (ultimo_tick - inizio_gap)
                if b.stanza_attesa_prepara(ora=ultimo_tick):
                    b.stanza_attesa_scalda()
            # La domanda: la sua riga nella stanza («→ Calliope») appena detta
            riga(st, 1, DOMANDE[n].replace("Calliope, ", ""), t - 2.5, "Carlo",
                 durata=2.0, rivolta="si")
            b.last_turn_at = time.monotonic() - gap
            b.stanza_turno = ctx_mod.costruisci(st, 1, cfg, t)
            "".join(b.stream_reply(DOMANDE[n], "amministra"))
            s = b.last_stanza_storia or {}
            # I pezzi in attesa legati a questa frase non hanno la frase stessa
            segni = b.history[-2].get("_stanza") if len(b.history) >= 2 else None
            segni = segni if isinstance(segni, list) else [segni]
            domanda_in_attesa = any(
                q.n in segni and getattr(q, "in_attesa", False)
                and DOMANDE[n].replace("Calliope, ", "") in q.testo for q in b.conv.stanza)
            out.append({"turno": n + 1, "riletti": b.backend.turni[-1],
                        "sfondo": sum(b.backend.sfondo) - sfondo_prima,
                        "nuove": s.get("nuove", 0), "nuove_car": s.get("nuove_caratteri", 0),
                        "attesa": s.get("attesa", 0), "attesa_car": s.get("attesa_caratteri", 0),
                        "riapertura": gap > cfg.storia_inattiva_s,
                        "scaldate": (scaldate_prima, len(b.backend.scaldate)),
                        "domanda_in_attesa": domanda_in_attesa})
            t += 3.0
    finally:
        ctx_mod.RIAPERTURA_MAX_S = salva
    return b, st, out


def _stanza_msgs(msgs):
    return [m for m in msgs if "fonte: stanza" in str(m.get("content"))]


def prova_misura(stampa: bool):
    b_p, st_p, prima = giro(False)
    b_d, st_d, dopo = giro(True)
    rp = [m["riletti"] for m in prima]
    rd = [m["riletti"] for m in dopo]
    if stampa:
        print("\nToken riletti alla domanda (stima a messaggi della cache di Ollama), conversazione "
              "finta come quella dell'auto del 14/10 sera")
        print("turno  righe nuove  riapertura   prima   dopo  (di cui in attesa, già in cache)  "
              "letti in secondo piano")
        for p, d in zip(prima, dopo):
            print(f"{p['turno']:>5}  {COPIONE[p['turno'] - 1][0]:>11}  "
                  f"{'sì' if p['riapertura'] else '':>10}  {p['riletti']:>6} {d['riletti']:>6}  "
                  f"{d['attesa']:>6} righe, {d['attesa_car']:>5} car.  {d['sfondo']:>8}")
        print(f"p50 prima {statistics.median(rp)}, dopo {statistics.median(rd)}; "
              f"p90 prima {sorted(rp)[int(len(rp) * 0.9)]}, dopo {sorted(rd)[int(len(rd) * 0.9)]}; "
              f"in tutto prima {sum(rp)}, dopo {sum(rd)} (+{sum(m['sfondo'] for m in dopo)} in "
              "secondo piano)\n")
    verifica("misura: token riletti alla domanda, mediana e p90 più bassi col pezzo in attesa",
             statistics.median(rd) < statistics.median(rp)
             and sorted(rd)[int(len(rd) * 0.9)] < sorted(rp)[int(len(rp) * 0.9)],
             f"prima {rp}, dopo {rd}")
    # Ciò che si legge in secondo piano è il resto: le righe in attesa non spariscono
    verifica("misura: righe in attesa usate al turno dopo, nessuna persa fuori dalle riaperture "
             "(le stesse righe di prima, al turno o in attesa)",
             sum(1 for d in dopo if d["attesa"]) >= 3
             and [d["nuove"] + d["attesa"] for d in dopo if not d["riapertura"]]
             == [p["nuove"] for p in prima if not p["riapertura"]],
             f"dopo {[(d['nuove'], d['attesa']) for d in dopo]}, prima "
             f"{[p['nuove'] for p in prima]}")
    # La richiesta del turno comincia con la richiesta scaldata (senza il «ciao») byte per byte
    ok = True
    utili = [i for d in dopo if not d["riapertura"] for i in range(*d["scaldate"])]
    for sc in [b_d.backend.scaldate[i] for i in utili]:
        corpo = sc[:-1]
        dopo_sc = [r for r in b_d.backend.richieste if len(r) > len(corpo)]
        succ = next((r for r in dopo_sc if [_chiave(m) for m in r[:len(corpo)]]
                     == [_chiave(m) for m in corpo]), None)
        ok = ok and succ is not None
    verifica("cache: ogni prefisso scaldato è l'inizio, byte per byte, della richiesta dopo "
             "(fuori dalle attese finite in una riapertura, dove si butta)",
             ok and bool(utili), f"{len(utili)} su {len(b_d.backend.scaldate)} riscaldamenti")
    # Ogni riga al più una volta per conversazione, nell'ordine; la domanda mai in attesa
    ultimo = b_d.backend.richieste[-1]
    testo = "\n".join(str(m.get("content")) for m in _stanza_msgs(ultimo))
    righe_tutte = [r["testo"] for r in st_d.registro(1).righe()]
    presenti = [x for x in righe_tutte if x in testo]
    conte = [testo.count(x) for x in presenti]
    pos = [testo.find(x) for x in presenti]
    verifica("righe: ognuna una volta sola e nell'ordine, anche con i pezzi in attesa",
             conte == [1] * len(conte) and pos == sorted(pos) and len(presenti) > 10,
             f"{len(presenti)} righe")
    verifica("righe: in busta (fonte «stanza»)",
             all(prov.fonti([m]) == {"stanza"} for m in _stanza_msgs(ultimo)))
    verifica("righe: la frase della domanda appena detta mai nel pezzo in attesa del suo turno",
             not any(d["domanda_in_attesa"] for d in dopo))
    # Riapertura: il tetto
    riap = [d for d in dopo if d["riapertura"]]
    verifica("riapertura: il primo pezzo della conversazione nuova sta nel tetto di "
             "stanza_riapertura_caratteri (con l'intestazione e le righe degli ultimi 45 s)",
             all(d["nuove_car"] + d["attesa_car"] <= 3000 + 1200 for d in riap)
             and all(p["nuove_car"] > 3000 for p in prima if p["riapertura"]),
             f"dopo {[d['nuove_car'] for d in riap]}, prima "
             f"{[p['nuove_car'] for p in prima if p['riapertura']]}")
    st_p.chiudi()
    st_d.chiudi()


def _pronto(righe_prima=6):
    """Una conversazione aperta con un turno fatto e `righe_prima` righe nuove dopo."""
    cfg = cfg_base(stanza_attesa_caratteri=300)
    st = nuova_stanza(cfg)
    b = brain(cfg, st)
    t = time.time() - 120
    for j in range(4):
        riga(st, 1, f"{CHIACCHIERE[j]} (a.{j})", t + j * 5, ("Carlo", "Nicola")[j % 2])
    b.stanza_turno = ctx_mod.costruisci(st, 1, cfg, t + 25)
    "".join(b.stream_reply("Calliope, che ore sono?", "amministra"))
    for j in range(righe_prima):
        riga(st, 1, f"{CHIACCHIERE[4 + j]} (b.{j})", t + 40 + j * 6, ("Carlo", "Nicola")[j % 2])
    return cfg, st, b, t


def prova_contrari():
    cfg, st, b, t = _pronto()
    b.__dict__["_in_risposta"] = True
    verifica("contrario: durante una risposta niente pezzo in attesa",
             b.stanza_attesa_prepara(ora=t + 90) is False and not b.conv.stanza_attesa)
    b.__dict__["_in_risposta"] = False
    b.last_turn_at = time.monotonic() - 299
    verifica("contrario: con la conversazione in scadenza (si chiuderà al turno dopo) niente",
             b.stanza_attesa_prepara(ora=t + 90) is None)
    b.last_turn_at = time.monotonic() - 30
    verifica("contrario: righe sotto stanza_attesa_caratteri non si fissano",
             (lambda: (setattr(b.cfg, "stanza_attesa_caratteri", 99999),
                       b.stanza_attesa_prepara(ora=t + 90))[1])() is False)
    b.cfg.stanza_attesa_caratteri = 300
    # Quiete: le righe degli ultimi 4 s aspettano il turno
    verifica("quiete: con l'ultima riga appena finita resta fuori dal pezzo in attesa",
             b.stanza_attesa_prepara(ora=t + 40 + 5 * 6 + 4 + 1) is True
             and "(b.5)" not in b.conv.stanza_attesa[-1].testo
             and "(b.4)" in b.conv.stanza_attesa[-1].testo)
    st.chiudi()
    cfg, st, b, t = _pronto()
    st.pausa(1, 30) if hasattr(st, "pausa") else None
    in_pausa = False
    try:
        in_pausa = st.stato_pausa(1) is not None
    except Exception:  # noqa: BLE001
        pass
    if in_pausa:
        verifica("contrario: in pausa per ospiti niente pezzo in attesa",
                 b.stanza_attesa_prepara(ora=t + 90) is False)
    st.chiudi()
    cfg, st, b, t = _pronto()
    b.cfg.stanza_attesa = False
    verifica("contrario: stanza_attesa false → niente", b.stanza_attesa_prepara(ora=t + 90) is None)
    b.cfg.stanza_attesa = True
    b.cfg.stanza_contesto = False
    verifica("contrario: stanza spenta → niente", b.stanza_attesa_prepara(ora=t + 90) is None)
    b.cfg.stanza_contesto = True
    st.chiudi()
    # «Dimentica»: le righe non più nel registro portano via il pezzo in attesa
    cfg, st, b, t = _pronto()
    verifica("dimentica: prima il pezzo in attesa c'è", b.stanza_attesa_prepara(ora=t + 90) is True)
    st.dimentica(1) if hasattr(st, "dimentica") else st.registro(1).dimentica()
    b.stanza_turno = None
    "".join(b.stream_reply("Calliope, e adesso?", "amministra"))
    req = b.backend.richieste[-1]
    verifica("dimentica: il pezzo in attesa non arriva al modello",
             not any("(b." in str(m.get("content")) for m in req)
             and not b.conv.stanza_attesa)
    st.chiudi()
    # Senza righe nuove nel turno, il pezzo in attesa arriva lo stesso, legato alla frase
    cfg, st, b, t = _pronto()
    b.stanza_attesa_prepara(ora=t + 90)
    b.stanza_turno = None
    "".join(b.stream_reply("Calliope, cosa diceva Nicola?", "amministra"))
    req = b.backend.richieste[-1]
    pos_u = max(i for i, m in enumerate(req) if m.get("role") == "user")
    verifica("attesa senza blocco del turno: il pezzo davanti alla frase, prima dei dati del turno",
             any("(b.0)" in str(m.get("content")) for m in req[:pos_u])
             and isinstance(b.history[-2].get("_stanza"), int))
    st.chiudi()


def prova_riapertura():
    """La finestra del primo pezzo arriva all'inizio dell'ultimo scambio (la risposta di Calliope
    di nove minuti prima), e un silenzio lungo la ferma."""
    cfg = cfg_base()
    ora = time.time()
    righe = []
    # Uno scambio fitto da 12 minuti fa a ora, con la risposta di Calliope 9 minuti fa
    for j in range(25):
        righe.append({"inizio": ora - 720 + j * 28, "fine": ora - 720 + j * 28 + 4,
                      "testo": f"riga {j}"})
    righe.append({"inizio": ora - 545, "fine": ora - 540, "testo": "la cresima è il diciotto",
                  "chi": "calliope"})
    righe.sort(key=lambda r: r["inizio"])
    f = ctx_mod._finestra_scambio(righe, ora, cfg)
    verifica("riapertura: la finestra arriva all'inizio dello scambio (oltre gli 8 minuti)",
             any(r["testo"] == "la cresima è il diciotto" for r in f) and len(f) == len(righe))
    # Contrario: un silenzio di oltre stanza_scambio_pausa_s ferma la finestra agli 8 minuti
    vecchie = [{"inizio": ora - 1500, "fine": ora - 1496, "testo": "vecchia"}]
    f2 = ctx_mod._finestra_scambio(vecchie + [r for r in righe if r["fine"] > ora - 400], ora, cfg)
    verifica("riapertura, contrario: dopo un silenzio lungo la riga vecchia resta fuori",
             not any(r["testo"] == "vecchia" for r in f2))


def prova_misure():
    from calliope.stanza import misure as misure_mod
    turni_ = [{"stanza": {"contesto": {"righe": 30, "caratteri": 4000},
                          "storia": {"nuove": 2, "nuove_caratteri": 300, "attesa": 20,
                                     "attesa_caratteri": 2500, "righe": 60, "caratteri": 7000,
                                     "pezzi": 5}},
               "prima_frase_s": 1.1, "cache": {"riletti": 300}}]
    t = misure_mod.testo(misure_mod.riassunto([], turni_))
    verifica("misure: le righe già in cache (pezzo in attesa) in `calliope stato --turni`",
             "pezzo in attesa) in 1 turni, 20 righe" in t, t)
    c = Config()
    verifica("configurazione: pezzo in attesa acceso di serie (600 caratteri, ogni 5 s), "
             "riapertura 3000", (c.stanza_attesa, c.stanza_attesa_caratteri, c.stanza_attesa_ogni_s,
                                 c.stanza_riapertura_caratteri) == (True, 600, 5.0, 3000))
    import calliope.main as main_mod
    src = open(main_mod.__file__, encoding="utf-8").read()
    verifica("servizio: il thread delle righe in attesa acceso per ogni Brain (voce e corsie)",
             src.count("attesa_thread = True") == 2)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    prova_misura("--misura" in sys.argv)
    prova_contrari()
    prova_riapertura()
    prova_misure()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
