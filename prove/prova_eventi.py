"""
Il registro degli eventi, a secco (10/10/2026, passo 1 del § 8 di
docs/ricerche/2026-10-10-registro-eventi.md): `prova_eventi_tipi`, `prova_eventi_pure`,
`prova_eventi_partizione`, `prova_eventi_porte`, più quelle del § 2.6 che si fanno già in ombra
(due corsie della stessa persona, riassegnazione).

    python prove/prova_eventi.py

- **Tipi** (§ 2.2, § 10 punto 4): ogni tipo ha la sua riga nella proiezione del contesto e in
  quella del registro dei turni (resa o ESCLUSO con il motivo); tipi, visibilità e campi
  controllati alla scrittura; ciò che va su disco (sfida, dati non fidati, foto, riservati, «mai»,
  i campi solo in memoria).
- **Pure** (§ 10 punto 2): `proiezioni.py` importa solo `eventi.tipi` e la libreria standard,
  niente orologio né caso, al più 600 righe; stessi eventi, stessi byte.
- **Partizione** (§ 11.2): un adulto, un minore e un ospite di fantasia su due satelliti insieme;
  nessun evento di una conversazione nella proiezione di un'altra; nessuna API che legga più
  registri; il testo del minore fermato non va su disco.
- **Porte** (§ 2.5): chi scrive negli eventi (AST); annuncio nel registro di chi l'ha chiesto,
  avviso al tutore senza le frasi del minore, coda solo alla stessa persona.
- **Due corsie, stessa persona** (§ 2.6 a): due satelliti a 100 ms, turni interi, `seq` senza
  buchi. **Riassegnazione** (§ 2.6 c): il turno esce dall'anonimo ed entra nella persona, senza
  riscrivere niente.

Nomi di fantasia; niente rete, audio né modelli: ~1 s.
"""
import ast
import json
import os
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope.conversazione import Conversazione  # noqa: E402
from calliope.eventi import ombra as ombra_mod, proiezioni  # noqa: E402
from calliope.eventi import registro as registro_mod  # noqa: E402
from calliope.eventi.registro import (Disco, Registri, porta_annuncio,  # noqa: E402
                                      porta_coda, porta_riassegna, porte_usate)
from calliope.eventi.tipi import (TIPI, VIS, Evento, EventoNonValido, controlla,  # noqa: E402
                                  da_riga, per_disco, riga)

RADICE = Path(__file__).resolve().parent.parent
PORTE = tuple(f"porta_{n}" for n in registro_mod.PORTE)
errori = 0


def verifica(nome, ok, info=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({info})" if info and not ok else ""),
          flush=True)


# Il § 2.2 del progetto: l'elenco chiuso
TIPI_PROGETTO = {
    "conversazione_aperta", "conversazione_chiusa", "detto_persona", "trascrizione_capita",
    "dato_in_ingresso", "foto_in_ingresso", "allegato_in_ingresso", "dati_del_turno",
    "passata_modello", "chiamata_tool", "esito_tool", "detto_calliope", "voce_fine",
    "interruzione", "proposta_aperta", "proposta_chiusa", "sfida_chiesta", "sfida_esito",
    "modulo_compilato", "turno_escluso", "compressione", "scheda_mandata", "turno_riassegnato",
    "turno_chiuso"}


def ev(tipo, vis=None, **dati):
    v = controlla(tipo, vis, dati)
    return Evento("persona:p-ginevra", 1, "c1", None, 0.0, tipo, 1, v, dati)


# ─────────────────────────── tipi ───────────────────────────
def prova_tipi():
    print("— tipi: proiezione per ogni tipo, controlli, disco")
    verifica("l'elenco chiuso dei tipi è quello del § 2.2", set(TIPI) == TIPI_PROGETTO,
             str(set(TIPI) ^ TIPI_PROGETTO))
    verifica("ogni tipo ha la sua riga nella proiezione del contesto e nel registro dei turni",
             set(proiezioni.PROIEZIONE_CONTESTO) == set(TIPI)
             == set(proiezioni.PROIEZIONE_TURNI))
    esclusi = [k for k, v in proiezioni.PROIEZIONE_CONTESTO.items()
               if isinstance(v, proiezioni.Escluso)]
    verifica("ogni ESCLUSO ha il suo motivo", esclusi and all(
        len(str(proiezioni.PROIEZIONE_CONTESTO[k]).strip()) > 10 for k in esclusi))
    verifica("ogni tipo ha una visibilità predefinita valida",
             all(t.vis in VIS for t in TIPI.values()))
    for nome, args in (("tipo sconosciuto", ("detto_qualcuno", None, {})),
                       ("visibilità sconosciuta", ("detto_persona", "tutti", {})),
                       ("campo non del tipo", ("detto_persona", None, {"umore": "ok"}))):
        try:
            controlla(*args)
            rifiutato = False
        except EventoNonValido:
            rifiutato = True
        verifica(f"rifiutato alla scrittura: {nome}", rifiutato)
    # Su disco (§ 2.4)
    d = per_disco(ev("detto_persona", testo="girasole treno", sfida=True))
    verifica("su disco: le parole della sfida mai", "testo" not in d, str(d))
    d = per_disco(ev("dato_in_ingresso", fonte="web", testo="Istruzioni nascoste nel sito"))
    verifica("su disco: il testo d'altri no, solo fonte e caratteri",
             "testo" not in d and d.get("caratteri") == 28, str(d))
    d = per_disco(ev("foto_in_ingresso", testo="[Foto 1: scontrino] ", numeri=[1]))
    verifica("su disco: la foto solo come riferimento", "testo" not in d and d["numeri"] == [1])
    d = per_disco(ev("esito_tool", id="c1", nome="archivio_cerca", contenuto='{"iban": "IT00"}',
                     riservato=True))
    verifica("su disco: il risultato riservato solo come traccia", "IT00" not in json.dumps(d))
    d = per_disco(ev("esito_tool", id="c2", nome="web_cerca", contenuto="x" * 50,
                     non_fidato=True))
    verifica("su disco: il risultato non fidato solo come lunghezza",
             json.loads(d["contenuto"]) == {"caratteri": 50})
    d = per_disco(ev("dati_del_turno", blocchi=[{"nome": "ricordi", "testo": "Ginevra ama il tè"}]))
    verifica("su disco: i dati del turno solo nomi e lunghezze",
             d["blocchi"] == [{"nome": "ricordi", "caratteri": len("Ginevra ama il tè")}])
    d = per_disco(ev("sfida_chiesta"))
    verifica("su disco: un evento «mai» non ha dati", d == {})
    d = per_disco(ev("detto_persona", testo="frase di un minore fermata", canale="voce",
                     _non_su_disco=["testo"]))
    verifica("su disco: i campi solo in memoria (_non_su_disco) non ci vanno",
             "testo" not in d and "_non_su_disco" not in d, str(d))
    e1 = ev("detto_calliope", testo="Sono le dieci.", autore="contenuto", atto="risposta",
            frase=0, canale="voce")
    r = riga(e1)
    e2 = da_riga((r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[10], r[11]))
    verifica("riga e rigioco: lo stesso evento", e2 == e1 and riga(e2) == r)
    try:
        da_riga(("persona:x", 1, "c", None, 0.0, "detto_persona", 1, "modello", '{"te', 1))
        rotta = False
    except ValueError:
        rotta = True
    verifica("una riga rovinata solleva ValueError (il rigioco si ferma lì)", rotta)
    doc = (RADICE / "docs" / "aree" / "voce-e-regole.md").read_text(encoding="utf-8")
    verifica("la ricetta «come aggiungere un tipo di evento» è nel documento d'area",
             "Come aggiungere un tipo di evento" in doc)


# ─────────────────────────── proiezioni pure ───────────────────────────
def prova_pure():
    print("— proiezioni pure: import, niente orologio né caso, tetto di righe, determinismo")
    p = RADICE / "calliope" / "eventi" / "proiezioni.py"
    testo = p.read_text(encoding="utf-8")
    albero = ast.parse(testo)
    importati = set()
    for n in ast.walk(albero):
        if isinstance(n, ast.Import):
            importati |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            importati.add(("." * n.level) + (n.module or ""))
    ammessi = {"__future__", "dataclasses", "json", ".tipi"}
    verifica("proiezioni.py importa solo eventi.tipi e la libreria standard (niente time, "
             "random, Brain, ciclo)", importati <= ammessi, str(importati - ammessi))
    nomi = {n.id for n in ast.walk(albero) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(albero) if isinstance(n, ast.Attribute)}
    verifica("…e non tocca orologio, caso, Brain né il ciclo",
             not nomi & {"time", "random", "uuid", "monotonic", "perf_counter", "brain",
                         "Brain", "ciclo", "Ciclo", "history"}, str(nomi & {"time", "random"}))
    righe = len(testo.splitlines())
    verifica(f"tetto di 600 righe per proiezioni.py ({righe})", righe <= 600)
    reg = registro_mod.Registro("persona:p-ginevra")
    reg.apri("persona", 1, riassunto="L'ultima volta avete parlato del mare.",
             riassunto_tipo="ripresa")
    s = reg.aggiungi("detto_persona", 1, testo="Che ore sono?", canale="voce", brain=True).seq
    reg.aggiungi("chiamata_tool", 1, id="c1", nome="ora_attuale", argomenti={})
    reg.aggiungi("esito_tool", 1, id="c1", nome="ora_attuale",
                 contenuto=json.dumps({"ora": "10:00"}))
    reg.aggiungi("detto_calliope", 1, testo="Vediamo…", autore="atto", atto="attesa", frase=0,
                 canale="voce", vis="registro")
    reg.aggiungi("detto_calliope", 1, testo="Sono le dieci.", autore="contenuto",
                 atto="risposta", frase=1, canale="voce")
    reg.aggiungi("voce_fine", 1, da=0, inviate=2, sentite=2, interrotta=False)
    reg.aggiungi("detto_persona", 2, testo="E a Tokyo?", canale="voce", brain=True)
    reg.aggiungi("detto_calliope", 2, testo="A Tokyo sono le diciassette.", autore="contenuto",
                 atto="risposta", frase=0, canale="voce")
    reg.aggiungi("voce_fine", 2, da=0, inviate=1, sentite=1, interrotta=False)
    eventi = reg.eventi()
    a = json.dumps(proiezioni.contesto(eventi), sort_keys=True, ensure_ascii=False)
    b = json.dumps(proiezioni.contesto(tuple(eventi)), sort_keys=True, ensure_ascii=False)
    verifica("stessi eventi, stessi byte (due volte)", a == b)
    msgs = proiezioni.contesto(eventi)
    verifica("la frase d'attesa non entra nel contesto, il riassunto sì, in testa",
             "Vediamo" not in a and msgs[0] == {"role": "system", "content":
                                                 "L'ultima volta avete parlato del mare."})
    verifica("l'ora del turno di prima è «di allora» (forma definitiva, come Brain)",
             "ora_di_allora" in json.dumps(msgs), json.dumps(msgs)[:300])
    verifica("la finestra (`da`): i turni prima non si proiettano",
             all("Che ore sono" not in str(m.get("content")) for m in
                 proiezioni.contesto(eventi, da=s + 1)))
    with tempfile.TemporaryDirectory() as tmp:
        d = Disco.file(os.path.join(tmp, "c.db"))
        reg2 = registro_mod.Registro("persona:p-ginevra", d)
        for e in eventi:
            reg2.aggiungi(e.tipo, e.turno, vis=e.vis, **e.dati)
        d.scrivi()
        r = Registri(Disco.file(os.path.join(tmp, "c.db")), log=lambda m: None)
        r.riprendi(0)
        c = json.dumps(proiezioni.contesto(r.della_corsia("persona:p-ginevra").eventi()),
                       sort_keys=True, ensure_ascii=False)
        verifica("…e dopo il rigioco dal disco", c == a)
        d.db.close()
        r.disco.db.close()


# ─────────────────────────── partizione ───────────────────────────
def _turno(reg, testo, risposta, corsia, turno, pausa=0.0, **extra):
    with reg.lotto():
        if reg.conv is None:
            reg.apri("persona" if not reg.ospite else "anonima", turno, corsia)
        reg.aggiungi("detto_persona", turno, corsia=corsia, testo=testo, canale="voce",
                     brain=True, **extra)
        for i, f in enumerate(risposta):
            time.sleep(pausa)
            reg.aggiungi("detto_calliope", turno, corsia=corsia, testo=f, autore="contenuto",
                         atto="risposta", frase=i, canale="voce")
        reg.aggiungi("voce_fine", turno, corsia=corsia, da=0, inviate=len(risposta),
                     sentite=len(risposta), interrotta=False)
        reg.aggiungi("turno_chiuso", turno, corsia=corsia, esito="risposta", regole=[])


def prova_partizione():
    print("— partizione: adulto, minore e ospite su due satelliti insieme")
    with tempfile.TemporaryDirectory() as tmp:
        d = Disco.file(os.path.join(tmp, "c.db"))
        r = Registri(d, log=lambda m: None)
        frasi = {"persona:p-ginevra": ("Ginevra: ricordami il dentista.", ["Va bene, Ginevra."]),
                 "persona:p-tommaso": ("Tommaso: ho paura del buio.", ["Ci sono io."]),
                 "ospite:sat:cucina": ("Ospite: dov'è il bagno?", ["In fondo a destra."])}
        th = []
        for k, (testo, risp) in frasi.items():
            extra = {"_non_su_disco": ["testo"]} if "tommaso" in k else {}
            th.append(threading.Thread(target=_turno, args=(r.della_corsia(k), testo, risp,
                                                             "sat:studio" if "ginevra" in k
                                                             else "sat:cucina", 1, 0.002),
                                       kwargs=extra))
        for t in th:
            t.start()
        for t in th:
            t.join()
        r.scrivi()
        ok = True
        for k, (testo, risp) in frasi.items():
            c = json.dumps(proiezioni.contesto(r.della_corsia(k).eventi()), ensure_ascii=False)
            for k2, (t2, r2) in frasi.items():
                if k2 != k and (t2 in c or r2[0] in c):
                    ok = False
            ok = ok and testo in c
        verifica("nessun evento di una conversazione nella proiezione di un'altra", ok)
        pubblici = {n for n in dir(Registri) if not n.startswith("_")}
        verifica("Registri dà un registro per volta: nessuna API che legga più registri",
                 pubblici == {"della_corsia", "esiste", "chiavi", "scrivi", "dimentica",
                              "riprendi"}, str(pubblici))
        righe = d.db.execute("SELECT registro, dati FROM eventi WHERE tipo = 'detto_persona'"
                             ).fetchall()
        minore = [json.loads(x) for reg, x in righe if reg == "persona:p-tommaso"]
        verifica("il testo del minore fermato non va su disco (resta solo in memoria)",
                 minore and "testo" not in minore[0], str(minore))
        letti = {x[0] for x in d.db.execute("SELECT DISTINCT registro FROM eventi")}
        verifica("su disco partizionato per registro", letti == set(frasi), str(letti))
        d.db.close()


# ─────────────────────────── due corsie, stessa persona (§ 2.6 a) ───────────────────────────
def prova_due_corsie():
    print("— due satelliti, la stessa persona a 100 ms: turni interi, seq senza buchi")
    r = Registri(None, log=lambda m: None)
    reg = r.della_corsia("persona:p-ginevra")
    reg.apri("persona", 0)
    a = threading.Thread(target=_turno, args=(reg, "Dallo studio: che ore sono?",
                                              ["Sono", "le", "dieci."], "sat:studio", 1, 0.01))
    b = threading.Thread(target=_turno, args=(reg, "Dalla cucina: che tempo fa?",
                                              ["Sole", "e", "vento."], "sat:cucina", 2, 0.01))
    a.start()
    time.sleep(0.1)
    b.start()
    a.join()
    b.join()
    ev = reg.eventi()
    seq = [e.seq for e in ev]
    verifica("seq senza buchi", seq == list(range(seq[0], seq[0] + len(seq))), str(seq))
    corsie_ = [e.corsia for e in ev if e.tipo != "conversazione_aperta"]
    cambi = sum(1 for x, y in zip(corsie_, corsie_[1:]) if x != y)
    verifica("i due turni interi, uno dopo l'altro, mai mescolati", cambi == 1, str(corsie_))


# ─────────────────────────── riassegnazione (§ 2.6 c) ───────────────────────────
def prova_riassegna():
    print("— riassegnazione: dall'anonimo alla persona, senza riscrivere")
    r = Registri(None, log=lambda m: None)
    anon = r.della_corsia("ospite:sat:studio")
    _turno(anon, "Sì, aprilo.", ["Lo apro."], "sat:studio", 1)
    prima = tuple(anon.eventi())
    s = next(e.seq for e in prima if e.tipo == "detto_persona")
    e1, e2 = porta_riassegna(r, "ospite:sat:studio", s, "persona:p-ginevra", "ero_io",
                             "sat:studio")
    pa = json.dumps(proiezioni.contesto(anon.eventi()), ensure_ascii=False)
    pp = json.dumps(proiezioni.contesto(r.della_corsia("persona:p-ginevra").eventi()),
                    ensure_ascii=False)
    verifica("il turno esce dalla proiezione dell'anonimo", "Sì, aprilo." not in pa, pa)
    verifica("…ed entra in quella della persona, con riassegnato_da",
             "Sì, aprilo." in pp and e2.dati.get("riassegnato_da") == f"ospite:sat:studio#{s}")
    verifica("nessuna riscrittura: gli eventi d'origine sono quelli di prima più uno",
             anon.eventi()[:len(prima)] == prima and anon.eventi()[-1] == e1)
    verifica("l'anonimo non vede eventi della persona",
             all(e.registro == "ospite:sat:studio" for e in anon.eventi()))
    try:
        porta_riassegna(r, "persona:p-ginevra", e2.seq, "persona:p-ginevra", "x")
        stesso = False
    except EventoNonValido:
        stesso = True
    verifica("contrario: nello stesso registro si rifiuta", stesso)
    verifica("la porta ha il suo nome nel registro dei turni", "riassegna" in porte_usate())


# ─────────────────────────── porte (§ 2.5) ───────────────────────────
def prova_porte_ast():
    print("— porte: chi scrive negli eventi (AST)")
    fuori = []
    for p in (RADICE / "calliope").rglob("*.py"):
        rel = p.relative_to(RADICE).as_posix()
        if rel.startswith("calliope/eventi/"):
            continue
        albero = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(albero):
            if isinstance(n, ast.Attribute) and n.attr in ("della_corsia",) + PORTE:
                fuori.append(f"{rel}:{n.lineno} {n.attr}")
            if isinstance(n, ast.Name) and n.id in PORTE:
                fuori.append(f"{rel}:{n.lineno} {n.id}")
            if isinstance(n, ast.ImportFrom) and (n.module or "").endswith("eventi.registro"):
                nomi = {a.name for a in n.names}
                if nomi & ({"Registro"} | set(PORTE)):
                    fuori.append(f"{rel}:{n.lineno} import {sorted(nomi)}")
    verifica("fuori da calliope/eventi nessuno prende un registro né usa le porte",
             not fuori, str(fuori))
    om = ast.parse((RADICE / "calliope" / "eventi" / "ombra.py").read_text(encoding="utf-8"))
    ricevitori, assegnazioni = set(), []
    for n in ast.walk(om):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr in ("aggiungi", "apri", "chiudi") \
                and isinstance(n.func.value, ast.Name):
            ricevitori.add(n.func.value.id)
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "reg"
                                             for t in n.targets):
            if isinstance(n.value, ast.Constant) and n.value.value is None:
                continue
            f = n.value.func if isinstance(n.value, ast.Call) else None
            nome = (f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(
                f, ast.Name) else "?")
            assegnazioni.append(nome)
    verifica("nell'ombra si scrive solo nel registro `reg`", ricevitori == {"reg"},
             str(ricevitori))
    verifica("…che viene solo dal registro della corsia o da una porta",
             all(a in ("_registro", "della_corsia") or a.startswith("porta_")
                 for a in assegnazioni), str(assegnazioni))
    src = (RADICE / "calliope" / "eventi" / "ombra.py").read_text(encoding="utf-8")
    fn = src[src.index("    def _registro("):src.index("    def _scrivi_e_confronta(")]
    verifica("…e `_registro` restituisce solo della_corsia o una porta",
             "porta_annuncio(" in fn and "porta_avviso_tutore(" in fn
             and "della_corsia(" in fn and ".aggiungi(" not in fn)


class _Brain:
    def __init__(self, conv):
        self.conv, self.last_capito, self.last_sfida = conv, None, False


def _ombra(conv, registri):
    c = types.SimpleNamespace(brain=_Brain(conv), speaker=types.SimpleNamespace(
        played=[], interrupted=False), corsia=types.SimpleNamespace(chiave="sat:studio",
                                                                    nome="studio"),
        speaker_ctx=None, rule=lambda n: None)
    return ombra_mod.Ombra(types.SimpleNamespace(eventi="ombra"), registri, c,
                           log=lambda m: None), c


def prova_porte():
    print("— porte: annuncio a chi l'ha chiesto, avviso al tutore, coda solo alla stessa persona")
    r = Registri(None, log=lambda m: None)
    # Luca ha parlato per ultimo sul satellite; il lavoro finito è di Ginevra: annuncio_per ha messo
    # la conversazione di Ginevra nel turno, e l'evento va nel registro di Ginevra
    luca = Conversazione("persona:p-luca")
    _turno(r.della_corsia("persona:p-luca"), "Luca: che ore sono?", ["Le dieci."],
           "sat:studio", 1)
    ginevra = Conversazione("persona:p-ginevra")
    ginevra.history = [{"role": "assistant", "content": "Il riassunto del lavoro è pronto."}]
    o, c = _ombra(ginevra, r)
    o._finestra.append(("say", "Il riassunto del lavoro è pronto.", "annuncio", False))
    porte_usate()
    o.chiudi_turno(None)
    rec = {"esito": "risposta", "regole": []}
    o._finestra.clear()
    c.brain.conv = luca
    o.chiudi_turno(rec)
    pa = json.dumps(proiezioni.contesto(r.della_corsia("persona:p-ginevra").eventi()),
                    ensure_ascii=False)
    pl = json.dumps(proiezioni.contesto(r.della_corsia("persona:p-luca").eventi()),
                    ensure_ascii=False)
    verifica("annuncio del lavoro nel registro di chi l'ha chiesto (Ginevra), non di chi ha "
             "parlato per ultimo (Luca)", "riassunto del lavoro" in pa
             and "riassunto del lavoro" not in pl, pa + " | " + pl)
    verifica("…con la porta «annuncio» nel registro dei turni (al turno dopo)",
             "annuncio" in (rec.get("eventi_ombra") or {}).get("porte", []), str(rec))
    # Avviso del guardiano al tutore: nel registro del tutore, solo il testo detto
    r2 = Registri(None, log=lambda m: None)
    _turno(r2.della_corsia("persona:p-tommaso"), "Tommaso: ho paura del buio.",
           ["Ci sono io."], "sat:cameretta", 1)
    tutore = Conversazione("persona:p-ginevra")
    o2, _c = _ombra(tutore, r2)
    o2._finestra.append(("say", "Tommaso ha avuto paura stasera: parlatene insieme.",
                         "avviso_tutore", False))
    o2.chiudi_turno(None)
    pt = json.dumps(proiezioni.contesto(r2.della_corsia("persona:p-ginevra").eventi()),
                    ensure_ascii=False)
    verifica("avviso al tutore nel suo registro, senza le frasi del minore",
             "parlatene insieme" in pt and "ho paura del buio" not in pt, pt)
    verifica("…con la porta «avviso_tutore»", "avviso_tutore" in json.dumps(
        o2._riporto.get("eventi_ombra") or {}), str(o2._riporto))
    for da, a, nome in (("persona:p-ginevra", "persona:p-luca", "un'altra persona"),
                        ("ospite:sat:studio", "ospite:sat:studio", "un ospite")):
        try:
            porta_coda(r, da, a)
            rifiutata = False
        except EventoNonValido:
            rifiutata = True
        verifica(f"coda rifiutata verso {nome}", rifiutata)
    verifica("coda alla stessa persona: sì", porta_coda(r, "persona:p-ginevra", "persona:p-ginevra")
             is r.della_corsia("persona:p-ginevra"))
    try:
        porta_annuncio(r, "tutti")
        bad = False
    except EventoNonValido:
        bad = True
    verifica("annuncio: serve la chiave di una conversazione", bad)


def main():
    prova_tipi()
    prova_pure()
    prova_partizione()
    prova_due_corsie()
    prova_riassegna()
    prova_porte_ast()
    prova_porte()
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
