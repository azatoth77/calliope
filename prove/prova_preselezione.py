import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della preselezione dei tool System 1 (15/10, calliope/system1/preselezione.py;
progetto docs/ricerche/2026-10-15-preselezione-tool.md). Dal 16/10 (issue #25, scelta B) la
misura è chiusa come negativa (§ 7 della ricerca) e l'ombra nel ciclo è tolta: resta il decisore
come strumento di misura.

- prototipi dagli schemi (nome, prima frase, esempi tra «…»), codifica «parole»;
- il banco (prove/banco_preselezione.py, 148 frasi con i tool veri di un registro completo):
  il richiamo con il margine di serie (dal 16/10 un avviso, non un errore), almeno 40 frasi a
  «nucleo», e i contrari (con margine 0 il richiamo cade: il margine serve), tempi del decisore;
- i segnali di struttura: tool recente fuori dal nucleo, tool nominato nei dati del turno o
  nella proposta, foto → «tutti»; un nucleo con tool che non ci sono;
- l'ombra tolta (16/10): niente ganci in ciclo.py, main.py, stato.py, nessun campo in Config
  e in calliope.yaml; un locale con le chiavi di prima si segnala e non ferma l'avvio; lo
  script della DGX prende il nucleo da `--nucleo`; contrario: il decisore resta.
"""

from pathlib import Path

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
    # Dal 16/10 (#25) un avviso e non un errore: i prototipi vengono dalle descrizioni dei tool,
    # e una descrizione cambiata non deve far diventare rossa una misura che non si usa
    if presi < n:
        print(f"    AVVISO: richiamo {presi}/{n} sul banco con il margine di serie: {mancati[:5]}")
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


def prova_tolta():
    """Dal 16/10 (issue #25, scelta B): l'ombra nel ciclo è tolta, il decisore resta come
    strumento di misura (prove/manuali/preselezione_dgx.py --registro)."""
    for rel in ("calliope/ciclo.py", "calliope/main.py", "calliope/config.py"):
        src = (RADICE / rel).read_text(encoding="utf-8")
        righe = [r.strip() for r in src.splitlines() if "preselezione" in r]
        verifica(f"tolta: nessun «preselezione» in {rel}", not righe, str(righe[:3]))
    src = (RADICE / "calliope" / "stato.py").read_text(encoding="utf-8")
    verifica("tolta: niente sezione della preselezione in calliope stato --turni",
             "preselezione" not in src)
    c = Config()
    verifica("tolta: nessun campo preselezione_* in Config",
             not [k for k in vars(c) if k.startswith("preselezione")])
    yaml = (RADICE / "calliope.yaml").read_text(encoding="utf-8")
    verifica("tolta: nessun campo della preselezione in calliope.yaml",
             "preselezione_" not in yaml)
    verifica("tolta: il modulo non ha più l'ombra né i modi",
             not any(hasattr(ps, n) for n in ("OmbraPreselezione", "load_preselezione",
                                              "MODI", "riassunto")))
    # Il decisore resta (contrario: non si è tolto troppo)
    verifica("contrario: Preselettore, Richiesta, preso e il margine restano",
             all(hasattr(ps, n) for n in ("Preselettore", "Richiesta", "preso", "MARGINE",
                                          "CodificaParole", "CodificaEmbedding")))
    # Un locale con le chiavi di prima (la DGX aveva `preselezione_tool: spenta`; un «ombra»
    # rimasto) dà solo una segnalazione: l'avvio non si ferma e il resto del file vale
    import contextlib
    import io
    import os
    import tempfile
    from calliope.config import load_config
    tmp = Path(tempfile.mkdtemp())
    base = tmp / "calliope.yaml"
    base.write_text("llm:\n  llm_temperature: 0.7\n", encoding="utf-8")
    loc = tmp / "calliope.locale.yaml"
    loc.write_text("llm:\n  preselezione_tool: ombra\n  preselezione_margine: 0.1\n"
                   "  llm_temperature: 0.5\n", encoding="utf-8")
    vecchio = os.environ.get("CALLIOPE_CONFIG_LOCALE")
    os.environ["CALLIOPE_CONFIG_LOCALE"] = str(loc)
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            cfg = load_config(str(base))
        fermo = None
    except BaseException as e:  # noqa: BLE001 — è proprio ciò che non deve succedere
        cfg, fermo = None, e
    finally:
        if vecchio is None:
            os.environ.pop("CALLIOPE_CONFIG_LOCALE", None)
        else:
            os.environ["CALLIOPE_CONFIG_LOCALE"] = vecchio
    log = out.getvalue()
    ok = fermo is None and cfg is not None and cfg.llm_temperature == 0.5
    verifica("locale di prima: l'avvio non si ferma e il resto del locale vale", ok,
             "" if ok else repr(fermo))
    ok = ("Chiave sconosciuta «preselezione_tool»" in log
          and "Chiave sconosciuta «preselezione_margine»" in log)
    verifica("locale di prima: «preselezione_tool» segnalata come chiave sconosciuta", ok,
             "" if ok else log[-300:])
    verifica("locale di prima: nessun campo nuovo nato dalla chiave",
             cfg is not None and not hasattr(cfg, "preselezione_tool"))
    # Lo script della DGX non legge più la configurazione della preselezione
    src = (RADICE / "prove" / "manuali" / "preselezione_dgx.py").read_text(encoding="utf-8")
    verifica("preselezione_dgx.py: il nucleo da --nucleo, non da cfg.preselezione_*",
             "cfg.preselezione" not in src and '"--nucleo"' in src)


if __name__ == "__main__":
    prova_prototipi()
    prova_banco()
    prova_struttura()
    prova_tolta()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    sys.exit(1 if errori else 0)
