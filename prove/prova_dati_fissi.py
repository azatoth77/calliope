"""
Prova a secco della cache del prefisso con i dati del turno (16/10/2026, issue #95,
calliope/dati_turno.py, `dati_stabili_in_storia`, `dati_turno_tetto_token`).

Il motore finto registra le richieste; fra due richieste della stessa conversazione si conta ciò
che Ollama deve **riavvolgere**: i messaggi della richiesta di prima dopo il punto in cui la nuova
comincia a differire (token stimati). Con Gemma 4 (finestra scorrevole) oltre ~512 token veri la
cache si perde tutta e si rilegge la storia (`prove/manuali/banco_cache_swa.py`).

- **la cache**: 8 turni di chi amministra con ricordi e avvisi ai tutori: dal secondo turno ciò che
  si riavvolge sta sotto il tetto (`dati_turno_tetto_token`), la richiesta comincia con quella di
  prima fino ai dati del turno di allora, ricordi e avvisi una volta sola, davanti alla frase del
  turno in cui sono entrati; contrario: con `dati_stabili_in_storia: false` (come fino al 15/10) si
  riavvolge oltre il tetto a ogni turno;
- **un ricordo nuovo** a metà: un pezzo in più (in sola aggiunta), la cache resta;
- **un ricordo dimenticato**: le versioni vecchie escono (regola `dati_stabili_rifatti`), il ricordo
  non è più in nessuna richiesta, la guardia della cache non segna `rotta`, al turno dopo di nuovo
  sotto il tetto;
- **mai su disco**: la storia ha solo il segno `_dati`, `esporta` niente, l'archivio niente;
- **in compagnia** (conversazione condivisa) i ricordi tornano nei dati del turno e i pezzi escono;
- **il tetto**: la ricerca anticipata della stanza riceve i caratteri che restano sotto il tetto (e
  con il tetto a 0 nessun limite); `dati_turno_token` nel registro;
- **la misura**: `riletti_stimati` senza i byte delle foto; `stanza_potata` nel turno prima non
  fa scattare `rotta`; `ripresi` e i contatori di `calliope stato --turni`;
- **con `eventi: attivo`** il segno `_dati` arriva dall'evento della frase (solo in memoria): ciò
  che si riavvolge è lo stesso che con `ombra`.

Con `--misura` la tabella turno per turno prima/dopo. Nomi di fantasia. ~2 s.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calliope import latenza  # noqa: E402
from calliope.eventi import ombra as ombra_mod  # noqa: E402
from calliope.eventi.tipi import per_disco  # noqa: E402
from calliope.brain import CHARS_PER_TOKEN, _tokens_senza_foto  # noqa: E402
from calliope.conversazione import turni  # noqa: E402
from calliope.memory import HOUSE  # noqa: E402
from prova_stanza_storia import brain as brain_base, cfg_base, con_eventi, nuova_stanza  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio else ""),
          flush=True)


class Memoria:
    """I ricordi finti di Carlo e della casa."""

    def __init__(self):
        self.f = {"carlo-id": ["a Carlo piace la pizza margherita",
                               "Carlo corre il martedì e il giovedì mattina",
                               "il dentista di Carlo è il dottor Lanfranchi"],
                  HOUSE: ["la password del wifi è sul frigorifero",
                          "la caldaia si resetta col pulsante rosso"]}

    def facts(self, pid):
        return list(self.f.get(pid, ()))


AVVISI = ("Avvisi consegnati di recente a te come tutore (testi di Calliope, mai le parole del "
          "minore; non inventare dettagli): ieri alle 17:40, avviso «parole forti» per Nicola dal "
          "satellite «camera», consegnato sul telefono, stato: letto; oggi alle 08:10, avviso "
          "«richiesta insolita» per Nicola dal satellite «studio», consegnato a voce, stato: non "
          "ancora letto. Se te ne chiedono, rispondi con questi dati e la data; per il resto "
          "chiama i tool come sempre. ") * 2

DOMANDE = ["Calliope, che tempo fa domani?", "Calliope, mi consigli un libro?",
           "Calliope, quanto fa diciassette per tre?", "Calliope, come si fa il pane?",
           "Calliope, cosa vuol dire resilienza?", "Calliope, dimmi un proverbio.",
           "Calliope, qual è il fiume più lungo d'Italia?", "Calliope, grazie mille."]


def chiave(m):
    return json.dumps({k: v for k, v in m.items() if not k.startswith("_") and k != "images"},
                      ensure_ascii=False, sort_keys=True, default=str)


def riavvolti(prima, ora):
    """(token stimati della richiesta di prima dopo il punto di differenza, punto)."""
    a, b = [chiave(m) for m in prima], [chiave(m) for m in ora]
    k = 0
    for x, y in zip(a, b):
        if x != y:
            break
        k += 1
    return int(sum(len(x) for x in a[k:]) / CHARS_PER_TOKEN), k


def brain(cfg):
    b = brain_base(cfg, nuova_stanza(cfg))
    b.tool_ctx.memory = Memoria()
    return b


def turno(b, n, g=None, avvisi=True):
    if avvisi:
        b.avvisi_turno = AVVISI
    if g is not None:
        g.turno(DOMANDE[n % len(DOMANDE)], "amministra")
    else:
        "".join(b.stream_reply(DOMANDE[n % len(DOMANDE)], "amministra"))


def giro(fissi: bool, turni_n: int = 8, eventi: bool = False, prima_del_turno=None, **cfg_k):
    cfg = cfg_base(dati_stabili_in_storia=fissi, **cfg_k)
    b = brain(cfg)
    g = con_eventi(b) if eventi else None
    out = []
    for n in range(turni_n):
        if prima_del_turno:
            prima_del_turno(b, n)
        turno(b, n, g)
        v = b.backend.visti
        r, k = riavvolti(v[-2], v[-1]) if len(v) > 1 else (None, None)
        out.append({"turno": n + 1, "riavvolti": r, "punto": k,
                    "dati_turno": b.last_dati_turno_token,
                    "cache": dict(b.last_cache or {}), "regole": list(b.last_rules or ()),
                    "fissi": b.last_dati_fissi})
    return b, out


def conta(msgs, testo):
    return sum(testo in str(m.get("content") or "") for m in msgs)


# ─────────────────────────── 1. la cache ───────────────────────────
def prova_cache():
    tetto = 450
    b, dopo = giro(True)
    _, prima = giro(False)
    rd = [x["riavvolti"] for x in dopo[1:]]
    rp = [x["riavvolti"] for x in prima[1:]]
    verifica(f"cache: dal secondo turno si riavvolge sotto il tetto ({tetto} token stimati)",
             all(x <= tetto for x in rd), str(rd))
    verifica("contrario: con dati_stabili_in_storia false (come fino al 15/10) oltre il tetto a "
             "ogni turno", all(x > tetto for x in rp), str(rp))
    verifica("cache: i dati del turno (più la domanda) sotto il tetto in ogni turno, e il registro "
             "li conta", all(x["dati_turno"] is not None and x["dati_turno"] <= tetto
                              for x in dopo), str([x["dati_turno"] for x in dopo]))
    v = b.backend.visti
    ok = True
    for i in range(1, len(v)):
        prec, ora = v[i - 1], v[i]
        # Fino alla frase del turno prima esclusa, meno i dati del turno di allora (tutto ciò
        # che sta dopo l'ultimo messaggio di sistema dei dati fissi o della storia)
        u = max(j for j, m in enumerate(prec) if m.get("role") == "user")
        _, k = riavvolti(prec, ora)
        if k < u - 1:
            ok = False
    verifica("cache: ogni richiesta comincia con quella di prima fino ai dati del turno di allora",
             ok and not any(x["cache"].get("rotta") for x in dopo))
    ultimo = v[-1]
    verifica("ricordi e avvisi una volta sola nella richiesta (nei turni prima, non nei dati del "
             "turno)", conta(ultimo, "Ricordi salvati") == 1 and conta(ultimo, "Avvisi consegnati")
             == 1, f"{conta(ultimo, 'Ricordi salvati')} {conta(ultimo, 'Avvisi consegnati')}")
    utenti = [i for i, m in enumerate(ultimo) if m.get("role") == "user"]
    verifica("…davanti alla frase del primo turno, dove sono entrati",
             "Ricordi salvati" in str(ultimo[utenti[0] - 2].get("content"))
             and "Avvisi consegnati" in str(ultimo[utenti[0] - 1].get("content")),
             str([str(m.get("content"))[:30] for m in ultimo[utenti[0] - 3:utenti[0]]]))
    verifica("registro: i dati fissi visibili, solo nomi e numeri",
             dopo[0]["fissi"]["nuovi"] == ["ricordi", "avvisi"] and dopo[-1]["fissi"]["pezzi"] == 2
             and dopo[-1]["fissi"]["nuovi"] == [], str(dopo[-1]["fissi"]))
    verifica("la guardia della cache: riavvolti stimati nel registro",
             all(isinstance(x["cache"].get("riavvolti_stimati"), int) for x in dopo[1:])
             and dopo[-1]["cache"]["riavvolti_stimati"] <= tetto, str(dopo[-1]["cache"]))
    # Mai su disco
    js = json.dumps(b.conv.esporta(), ensure_ascii=False)
    verifica("mai su disco: la storia senza i pezzi, esporta senza il segno _dati",
             any("_dati" in m for m in b.history) and "_dati" not in js
             and "dentista" not in js and "Avvisi consegnati" not in js)
    verifica("…né nell'archivio dei turni",
             "dentista" not in json.dumps(turni(b.history), ensure_ascii=False))
    if "--misura" in sys.argv:
        print("\nToken stimati da riavvolgere per turno (Ollama con Gemma 4 perde la cache oltre "
              "~512 token veri), 8 turni di chi amministra con ricordi e avvisi")
        print("turno   prima (dati nel turno)   dopo (dati fissi nella storia)   dati del turno")
        for p, d in zip(prima, dopo):
            print(f"{p['turno']:>5}   {p['riavvolti']!s:>22}   {d['riavvolti']!s:>30}   "
                  f"{p['dati_turno']!s:>5} -> {d['dati_turno']!s}")
        print()


# ─────────────────────────── 2. ricordi che cambiano ───────────────────────────
def prova_ricordi():
    def cambia(b, n):
        if n == 3:
            b.tool_ctx.memory.f["carlo-id"].append("Carlo ha un gatto che si chiama Pepe")
        if n == 5:
            b.tool_ctx.memory.f["carlo-id"].remove("il dentista di Carlo è il dottor Lanfranchi")
    b, out = giro(True, prima_del_turno=cambia)
    v = b.backend.visti
    verifica("ricordo nuovo: un pezzo in più in sola aggiunta, la cache resta (sotto il tetto)",
             out[3]["fissi"]["nuovi"] == ["ricordi"] and out[3]["riavvolti"] <= 450
             and conta(v[3], "Ricordi salvati") == 2 and conta(v[3], "Pepe") == 1,
             str(out[3]))
    verifica("ricordo dimenticato: le versioni vecchie escono e la nuova entra intera "
             "(regola dati_stabili_rifatti)", "dati_stabili_rifatti" in out[5]["regole"]
             and out[5]["fissi"].get("rifatti") == ["ricordi"]
             and conta(v[5], "Ricordi salvati") == 1, str(out[5]["fissi"]))
    verifica("…e non è più in nessuna parte della richiesta",
             all("Lanfranchi" not in str(m.get("content")) for m in v[5])
             and all("Lanfranchi" not in str(m.get("content")) for m in v[7])
             and conta(v[5], "Pepe") == 1)
    verifica("…la guardia della cache non lo segna come rottura inattesa",
             not out[5]["cache"].get("rotta"), str(out[5]["cache"]))
    verifica("…al turno dopo di nuovo sotto il tetto", out[6]["riavvolti"] <= 450
             and out[7]["riavvolti"] <= 450, str([out[6]["riavvolti"], out[7]["riavvolti"]]))

    def scadono(b, n):
        if n >= 4:
            b.avvisi_turno = None
    cfg = cfg_base(dati_stabili_in_storia=True)
    b = brain(cfg)
    for n in range(6):
        b.avvisi_turno = AVVISI if n < 4 else None
        "".join(b.stream_reply(DOMANDE[n], "amministra"))
    verifica("avvisi scaduti: la versione di prima resta dov'era (era vera), nessun pezzo nuovo",
             conta(b.backend.visti[-1], "Avvisi consegnati") == 1
             and (b.last_dati_fissi or {}).get("nuovi") == [])


# ─────────────────────────── 3. contrari ───────────────────────────
def prova_contrari():
    cfg = cfg_base(dati_stabili_in_storia=True)
    b = brain(cfg)
    for n in range(3):
        turno(b, n)
    b.conv.condivisa = True
    turno(b, 3)
    ultimo = b.backend.visti[-1]
    utenti = [i for i, m in enumerate(ultimo) if m.get("role") == "user"]
    verifica("in compagnia (conversazione condivisa): i pezzi escono e i ricordi tornano nei dati "
             "del turno, di chi parla adesso", conta(ultimo, "Ricordi salvati") == 1
             and "Ricordi salvati" in str(ultimo[utenti[-1] - 2].get("content"))
             + str(ultimo[utenti[-1] - 1].get("content"))
             and not b.conv.dati_fissi and "dati_stabili_rifatti" in b.last_rules,
             str([str(m.get("content"))[:25] for m in ultimo[-4:]]))
    # Un ospite: nessun ricordo
    b = brain(cfg_base(dati_stabili_in_storia=True))
    b.tool_ctx.speaker_ctx.current_speaker = None
    "".join(b.stream_reply("Che ore sono?", "ospite"))
    verifica("contrario: un ospite non ha ricordi (niente pezzi)",
             not b.conv.dati_fissi and conta(b.backend.visti[-1], "Ricordi salvati") == 0)
    b.tool_ctx.speaker_ctx.current_speaker = "Carlo"
    # Il turno uscito dalla storia: il pezzo se ne va con lui, il blocco torna al turno in corso
    b = brain(cfg_base(dati_stabili_in_storia=True))
    for n in range(3):
        turno(b, n)
    primo = next(i for i, m in enumerate(b.history) if m.get("role") == "user")
    secondo = [i for i, m in enumerate(b.history) if m.get("role") == "user"][1]
    b.conv.togli_in_testa(secondo)
    turno(b, 3)
    ultimo = b.backend.visti[-1]
    utenti = [i for i, m in enumerate(ultimo) if m.get("role") == "user"]
    verifica("turno tolto dalla storia: i dati fissi tornano davanti alla frase di adesso, una "
             "volta", primo == 0 and conta(ultimo, "Ricordi salvati") == 1
             and (b.last_dati_fissi or {}).get("orfani") == 2
             and any("Ricordi salvati" in str(m.get("content"))
                     for m in ultimo[utenti[-2] + 1:utenti[-1]]), str(b.last_dati_fissi))


# ─────────────────────────── 4. il tetto e la ricerca anticipata ───────────────────────────
def prova_tetto():
    from calliope.tools import stanza as stanza_tool
    visti = []

    def anticipa_finta(ctx, frase, blocco=None, massimo=None):
        visti.append(massimo)
        if massimo is not None and massimo < 400:
            return stanza_tool.Anticipo(tetto=True)
        n = 2000 if massimo is None else massimo
        return stanza_tool.Anticipo(testo="R" * n, righe=3)

    vero = stanza_tool.anticipa
    stanza_tool.anticipa = anticipa_finta
    try:
        for tetto, atteso in ((450, "budget"), (0, "senza")):
            b = brain(cfg_base(dati_stabili_in_storia=True, dati_turno_tetto_token=tetto))
            reg = b.tools
            get0, allowed0 = reg.get, reg.allowed
            reg.get = lambda n, _g=get0: object() if n == "stanza_cerca" else _g(n)
            reg.allowed = lambda n, lv, _a=allowed0: True if n == "stanza_cerca" else _a(n, lv)
            visti.clear()
            for n in range(3):
                turno(b, n)
            if atteso == "budget":
                verifica("tetto: la ricerca anticipata riceve i caratteri che restano sotto il "
                         "tetto, e i dati del turno ci stanno",
                         all(isinstance(m, int) and 0 < m < int(450 * CHARS_PER_TOKEN)
                             for m in visti) and b.last_dati_turno_token <= 450
                         and not b.last_dati_turno_oltre
                         and "stanza_anticipo" in b.last_rules, f"{visti} {b.last_dati_turno_token}")
                pos = [i for i, m in enumerate(b.backend.visti[-1])
                       if str(m.get("content")).startswith("RRR")]
                utenti = [i for i, m in enumerate(b.backend.visti[-1]) if m.get("role") == "user"]
                verifica("…nel posto di sempre, dopo ora e chi parla, prima della domanda",
                         len(pos) == 1 and pos[0] < utenti[-1]
                         and "Dati del turno" in str(b.backend.visti[-1][pos[0] - 1]["content"]))
            else:
                verifica("contrario: con il tetto a 0 nessun limite alla ricerca anticipata (e "
                         "nessun turno «oltre»)", visti == [None, None, None]
                         and not b.last_dati_turno_oltre and b.last_dati_turno_token > 450,
                         f"{visti} {b.last_dati_turno_token}")
        # Il tetto troppo stretto: la ricerca non parte e resta la spinta verso stanza_cerca
        b = brain(cfg_base(dati_stabili_in_storia=True, dati_turno_tetto_token=60))
        reg = b.tools
        get0, allowed0 = reg.get, reg.allowed
        reg.get = lambda n, _g=get0: object() if n == "stanza_cerca" else _g(n)
        reg.allowed = lambda n, lv, _a=allowed0: True if n == "stanza_cerca" else _a(n, lv)
        turno(b, 0)
        verifica("tetto stretto: la ricerca anticipata non parte (regola anticipo_tetto) e il "
                 "turno è contato oltre il tetto", "anticipo_tetto" in b.last_rules
                 and "stanza_anticipo" not in b.last_rules and b.last_dati_turno_oltre)
    finally:
        stanza_tool.anticipa = vero


# ─────────────────────────── 5. le misure ───────────────────────────
def prova_misure():
    foto = [{"role": "system", "content": "x" * 350},
            {"role": "user", "content": "guarda", "images": ["A" * 200_000]}]
    verifica("riletti stimati: una foto vale un costo fisso, non i byte del suo base64",
             _tokens_senza_foto(foto) < 600, str(_tokens_senza_foto(foto)))
    b = brain(cfg_base(dati_stabili_in_storia=True))
    m1 = [{"role": "system", "content": "s"}, {"role": "user", "content": "a"},
          {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}]
    m2 = [{"role": "system", "content": "s"}, {"role": "user", "content": "A"},
          {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"},
          {"role": "assistant", "content": "d"}, {"role": "user", "content": "e"}]

    def misura(potata: bool):
        b._richiesta_prima = None
        b._fissi_cache, b._confine_cache = 1, 3
        b.last_rules = []
        b._misura_prefisso(m1)
        if potata:
            b.__dict__["_potata_prima"] = True
        b._misura_prefisso(m2)
        return dict(b.last_cache or {})
    verifica("guardia: una differenza dentro i turni definitivi è «rotta»", misura(False).get("rotta"))
    verifica("…ma non dopo la potatura delle righe della stanza nel turno prima (stanza_potata)",
             not misura(True).get("rotta") and "_potata_prima" not in b.__dict__)
    # calliope stato --turni
    base = {"inizio": "2026-10-16T10:00:00", "esito": "risposta", "prima_frase_s": 1.0}
    tt = ([dict(base, cache={"riletti": 4000, "riletti_stimati": 1500}, dati_turno_token=900,
                dati_turno_oltre=True) for _ in range(6)]
          + [dict(base, cache={"riletti": 400, "riletti_stimati": 350}, dati_turno_token=300)
             for _ in range(6)]
          + [dict(base, cache={"prima": True, "riletti": 9000})])
    d = latenza.giorno(tt)
    verifica("stato --turni: cache persa quando i riletti superano la stima, i dati del turno e "
             "i turni oltre il tetto", d["cache"] == {"n": 12, "perse": 6}
             and d["dati_turno"]["oltre"] == 6 and d["dati_turno"]["n"] == 12, json.dumps(
                 {k: d[k] for k in ("cache", "dati_turno")}))
    t = latenza.testo({"2026-10-16": d})
    verifica("…nel testo per il terminale", "cache del prefisso persa in 6 turni su 12" in t
             and "oltre il tetto in 6 turni" in t, t)
    verifica("contrario: il primo turno della conversazione non conta",
             latenza.cache_persa(tt[-1]) is None and latenza.cache_persa(tt[6]) is False)
    # ripresi dalla prima passata
    b.last_riletti = b.last_ripresi = None
    b._note_usage({"prompt": 20000, "in_cache": 18000, "output": 10})
    b._note_usage({"prompt": 20100, "in_cache": 20050, "output": 10})
    verifica("ripresi e riletti dalla prima passata del turno",
             b.last_ripresi == 18000 and b.last_riletti == 2000)


# ─────────────────────────── 6. con eventi: attivo ───────────────────────────
def prova_eventi():
    _, ombra = giro(True)
    b, attivo = giro(True, eventi=True)
    ro = [x["riavvolti"] for x in ombra[1:]]
    ra = [x["riavvolti"] for x in attivo[1:]]
    verifica("eventi attivo: si riavvolge come con ombra (sotto il tetto), ricordi e avvisi una "
             "volta", all(x <= 450 for x in ra) and conta(b.backend.visti[-1],
                                                           "Ricordi salvati") == 1,
             f"ombra {ro}, attivo {ra}")
    reg = b.proiettore.registri.della_corsia(b.conv.chiave)
    dette = [e for e in reg.eventi() if e.tipo == "detto_persona"]
    verifica("…il segno dati nell'evento della frase (il primo turno), mai su disco",
             dette and dette[0].dati.get("dati") == [1, 2]
             and not any("dati" in per_disco(e) for e in dette),
             str([e.dati.get("dati") for e in dette]))
    # Contrario: senza il segno nell'evento i dati fissi sono «orfani» a ogni risposta e tornano
    # davanti alla frase di adesso: si riavvolgono di nuovo
    vecchio = ombra_mod.Ombra._segni_persona
    ombra_mod.Ombra._segni_persona = lambda self, conv: {}
    try:
        _, senza = giro(True, eventi=True)
    finally:
        ombra_mod.Ombra._segni_persona = vecchio
    rs = [x["riavvolti"] for x in senza[1:]]
    verifica("contrario: senza il segno nell'evento si riavvolge oltre il tetto",
             all(x > 450 for x in rs), str(rs))


def main():
    prova_cache()
    prova_ricordi()
    prova_contrari()
    prova_tetto()
    prova_misure()
    prova_eventi()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
