"""apriGioco c'è già, la tappa consegnabile si chiude, il segnaposto non si scrive, a secco
(20/10/2026, issue #192; area agenti-estensioni e giochi).

Il banco del criterio di #174 sulla DGX del 20/10 (`--casi tris2,porte --giri 2`) faceva 1/6,
con l'accettazione nascosta verde al primo giro in 5 lavori su 6. Qui, con l'agente finto e la
sandbox col docker finto:

1. la frase «apriGioco e creaCaso ci sono già in gioco.test.js, senza require: non scriverli
   tu» la vede anche una correzione: nel contratto del gioco, in VINCOLO_CORREZIONE_GIOCO e nel
   rimando della riproduzione; contrari: il contratto dell'estensione e il rimando di un
   programma no;
2. un *.test.js di un gioco che definisce apriGioco o creaCaso: nel risultato di esegui_test il
   fatto del motore finto e la regola agente_motore_finto; contrari: le chiamate, i commenti, un
   file in sola lettura, un lavoro che non è un gioco;
3. alla tappa con lo stato consegnabile (decisione di chi amministra del 20/10) il lavoro si
   chiude «fatto» (regola agente_consegna_alla_tappa, a voce «non ha consegnato, ma ha finito»),
   con gli esempi verdi o con la riproduzione «riprodotto»; contrari: i test verdi senza
   controllo indipendente, i test dell'agente rossi, gli esempi rossi, la correzione senza un
   test che riproduce (e il suo rimando resta per il giro dopo);
4. scrivi_file e il «nuovo» di modifica_file rifiutano il segnaposto della compattazione
   (regola agente_segnaposto); contrari: un testo con le parentesi quadre, la scrittura vera;
(il suggerimento del palco con la pagina già «griglia» è in prova_gioco_palco, sezione 1b).

    python prove\\prova_apri_gioco_tappa.py
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
sys.path.insert(0, str(RADICE / "prove"))

import prova_agente_guida as G  # noqa: E402
import prova_porte_consegna as P  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def sezione(t):
    print(f"\n— {t}", flush=True)


def regole(lav) -> dict:
    return (lav.segnali or {}).get("regole") or {}


# ═══════════════════════════ 1. la frase anche in una correzione ═══════════════════════════

def prova_frase():
    sezione("1. «apriGioco e creaCaso ci sono già» anche in una correzione")
    from calliope.agenti.riproduzione import messaggio_agente
    from calliope.config import Config
    from calliope.estensioni import contratto
    from calliope.testi import APRI_GIOCO_C_E
    from calliope.tools.sviluppo import VINCOLO_CORREZIONE_GIOCO
    verifica("la frase dice di non scriverli", "non scriverli tu" in APRI_GIOCO_C_E
             and "senza require" in APRI_GIOCO_C_E)
    gioco = contratto.testo(Config(), "gioco")
    i = gioco.find(APRI_GIOCO_C_E)
    verifica("nel contratto del gioco, dove si descrive apriGioco (gioco.test.js)",
             i > 0 and "gioco.test.js (la partita vera con la macchina, apriGioco" in gioco[
                 max(0, i - 120):i], gioco[max(0, i - 200):i + 120])
    verifica("contrario: il contratto dell'estensione no",
             APRI_GIOCO_C_E not in contratto.testo(Config(), "estensione"))
    verifica("nei vincoli della correzione di un gioco (sviluppo_correggi)",
             APRI_GIOCO_C_E in VINCOLO_CORREZIONE_GIOCO
             and "motore finto" in VINCOLO_CORREZIONE_GIOCO, VINCOLO_CORREZIONE_GIOCO[-400:])
    for stato in ("uguale", "nessun_test"):
        m = messaggio_agente({"stato": stato}, "il mostro non si vede", gioco=True)
        verifica(f"nel rimando della riproduzione di un gioco («{stato}»)", APRI_GIOCO_C_E in m,
                 m[-300:])
    verifica("contrario: il rimando di un programma no",
             APRI_GIOCO_C_E not in messaggio_agente({"stato": "nessun_test"}, "x", gioco=False))
    # Il banco compone i vincoli come sviluppo_correggi: la correzione delle porte li riceve
    sys.path.insert(0, str(RADICE / "prove" / "manuali"))
    import banco_temperatura as B
    verifica("la correzione delle porte del banco li riceve",
             APRI_GIOCO_C_E in B.vincoli_correzione(B.casi()["porte"]))


# ═══════════════════════════ 2. il motore finto ═══════════════════════════

FINTO_FUNZIONE = """const { test } = require("node:test");
const assert = require("node:assert");
async function apriGioco(opzioni) {
  return { stato: () => ({ fase: "turno" }) };
}
test("parte", async () => {
  const g = await apriGioco({ seme: 1 });
  assert.strictEqual(g.stato().fase, "turno");
});
"""
FINTO_ASSEGNATO = """const { test } = require("node:test");
globalThis.creaCaso = (seme) => () => 0.5;
test("caso", () => {});
"""
SOLO_CHIAMATE = """const { test } = require("node:test");
const assert = require("node:assert");
// Non scrivere: async function apriGioco(o) { … } e nemmeno creaCaso = …
test("parte", async () => {
  const g = await apriGioco({ seme: 1 });
  const caso = creaCaso(3);
  assert.ok(g && caso);
});
"""


def prova_motore_finto(tmp: Path):
    sezione("2. un apriGioco scritto nei test: il fatto del motore finto")
    from calliope.agenti.ciclo import Lavoro, motore_finto, nota_motore_finto
    from calliope.testi import APRI_GIOCO_C_E
    sb = G.sandbox(tmp, "trova")
    sb.scrivi("gioco.test.js", FINTO_FUNZIONE)
    sb.scrivi("altro.test.js", FINTO_ASSEGNATO)
    sb.scrivi("chiama.test.js", SOLO_CHIAMATE)
    # Revisione della PR #194: un alias dal globale e un commento a blocco non sono un motore
    sb.scrivi("alias.test.js", "const apriGioco = globalThis.apriGioco;\n"
                               "let creaCaso = global . creaCaso;\n"
                               "/* async function apriGioco(o) {\n  return 1;\n} */\n")
    sb.scrivi("logica.js", "function apriGioco() {}\n")
    sb.scrivi("accettazione.test.js", "async function apriGioco() {}\n")
    sb.sola_lettura |= {"accettazione.test.js"}
    finti = motore_finto(sb)
    verifica("trovati: la funzione in gioco.test.js e l'assegnazione a globalThis",
             sorted(finti) == [("altro.test.js", "creaCaso"), ("gioco.test.js", "apriGioco")],
             str(finti))
    verifica("contrari: le chiamate e i commenti, un file che non è un test, un test in sola "
             "lettura, l'alias dal globale e il commento a blocco",
             not any(p in ("chiama.test.js", "logica.js", "accettazione.test.js",
                           "alias.test.js") for p, _ in finti), str(finti))
    n = nota_motore_finto([("gioco.test.js", "apriGioco")])
    verifica("il fatto: dove, perché e cosa fare, con la frase",
             "gioco.test.js definisce un suo apriGioco" in n and "motore finto" in n
             and "Toglilo" in n and APRI_GIOCO_C_E in n, n)
    if not shutil.which("node"):
        print("SALTATA IN PARTE: esegui_test vero, node non c'è")
        return
    from calliope.agenti.scheletri import file_gioco
    ag = G.agente()

    def esegui(nome, test_gioco=None, gioco=True):
        s = G.sandbox(tmp, nome)
        for k, v in file_gioco(2, 2).items():
            s.scrivi(k, v)
        if test_gioco is not None:
            s.scrivi("gioco.test.js", test_gioco)
        lav = Lavoro(nome, "estensione", "il tris")
        lav.gioco = gioco
        return lav, ag._strumento(lav, s, "esegui_test", {})
    lav, r = esegui("finto", FINTO_FUNZIONE)
    verifica("esegui_test con un apriGioco suo: il fatto nel risultato e la regola "
             "agente_motore_finto", "motore finto" in str(r.get("motore_finto"))
             and regole(lav).get("agente_motore_finto") == 1, str(r)[:400])
    lav, r = esegui("partenza")
    verifica("contrario: la partenza (apriGioco solo chiamato): niente", "motore_finto" not in r
             and not regole(lav).get("agente_motore_finto") and r.get("passano") is True,
             str(r)[:400])
    lav, r = esegui("non-gioco", FINTO_FUNZIONE, gioco=False)
    verifica("contrario: un lavoro che non è un gioco: niente", "motore_finto" not in r
             and not regole(lav).get("agente_motore_finto"), str(r)[:300])


# ═══════════════════════════ 3. la tappa consegnabile ═══════════════════════════

def _estensione(tmp, nome, passate, lav=None, sb=None, max_passi=3):
    """Un'estensione a tappe con gli esempi di accettazione (come prova_fasi_agente_2
    ._gira_tetto), che si può continuare: con `lav` e `sb` di un giro di prima il giro dopo.
    (lavoro, risultato, log, sandbox)."""
    import prova_fasi_agente_2 as F2
    from calliope.agenti import accettazione as acc
    from calliope.agenti.ciclo import Lavoro
    from calliope.agenti.scheletri import prepara_estensione
    from calliope.estensioni.prompt import controlla_consegna
    cli = G._Copione(passate)
    log = []
    ag = G.agente(cli, log)
    ag.max_passi = max_passi
    if sb is None:
        sb = G.sandbox(tmp, nome)
        prepara_estensione(sb)
        sb.scrivi("manifesto.json", json.dumps(F2.MANIFESTO))
        lav = Lavoro(nome, "estensione", "Un convertitore di distanze")
        lav.tappe = True
        an = acc.interpreta(F2.ANALISI, 3, True)
        sb.scrivi(acc.FILE, acc.test_python(an))
        sb.sola_lettura |= {acc.FILE}
        lav.accettazione = {"stato": "pronta", "file": True, "nome_file": acc.FILE,
                            "esempi": len(an["esempi"])}
    try:
        ris = ag.codice(lav, sb, controlla=lambda x: controlla_consegna(x))
    except Exception as e:  # noqa: BLE001 — Limite
        ris = {"eccezione": type(e).__name__, "motivo": str(e)}
    return lav, ris, log, sb


def _correzione(tmp, nome, passate, max_passi=3, tappe=True):
    """Una correzione di un programma, di serie a tappe, senza esempi: l'agente finto recita
    `passate`; al tetto del giro la tappa."""
    import prova_fasi_agente as F
    from calliope.agenti.ciclo import Lavoro
    cli = P.Copione(passate)      # anche le passate di sola prosa
    log = []
    ag = G.agente(cli, log)
    ag.max_passi = max_passi
    lav = Lavoro(nome, "codice", "una funzione che somma")
    lav.tappe = tappe
    lav.correzione = True
    lav.problema_correzione = "il risultato non è quello giusto"
    lav.file_iniziali = dict(F.PRIMA)
    sb = G.sandbox(tmp, nome)
    for k, v in F.PRIMA.items():
        sb.scrivi(k, v)
    try:
        ris = ag.codice(lav, sb)
    except Exception as e:  # noqa: BLE001 — Limite
        ris = {"eccezione": type(e).__name__, "motivo": str(e)}
    return lav, ris, log


def prova_tappa(tmp: Path):
    sezione("3. alla tappa con lo stato consegnabile si consegna d'ufficio")
    import prova_fasi_agente as F
    import prova_fasi_agente_2 as F2
    lav, ris, log = F2._gira_tetto(tmp, "esempi-verdi", F2.GIUSTA, tappe=True)
    verifica("gli esempi di accettazione e i test verdi alla tappa: «fatto», consegna_al_tetto "
             "«tappa» con gli esempi, la regola agente_consegna_alla_tappa",
             ris.get("esito") == "fatto" and ris.get("consegna_al_tetto") == "tappa"
             and ris.get("consegna_al_tetto_con") == "esempi"
             and regole(lav).get("agente_consegna_alla_tappa") == 1
             and "Chiuso da me alla tappa" in ris.get("riassunto", ""), f"{ris} {regole(lav)}")
    lav, ris, log = F2._gira_tetto(tmp, "test-rossi", F2.GIUSTA, tappe=True,
                                   extra={"test_mio.py": F2.ROSSO})
    verifica("contrario: esempi verdi ma un test dell'agente rosso: la tappa resta, il motivo "
             "in tappa_no", ris.get("esito") == "tappa"
             and lav.segnali.get("tappa_no") == "i test dell'agente non passano"
             and not regole(lav).get("agente_consegna_alla_tappa")
             and not lav.segnali.get("al_tetto_no"), f"{ris.get('esito')} {lav.segnali}")
    lav, ris, log = F2._gira_tetto(tmp, "esempi-rossi", F2.SBAGLIATA, tappe=True)
    verifica("contrario: gli esempi rossi: la tappa resta",
             ris.get("esito") == "tappa"
             and str(lav.segnali.get("tappa_no")).startswith("esempi di accettazione rossi"),
             f"{ris.get('esito')} {lav.segnali.get('tappa_no')}")
    lav, ris, log, cli, _ = P.gira(tmp, "senza-controllo", [P.SCRIVE_GIUSTO, [P.ESEGUI],
                                                            [P.LEGGI]], max_passi=3, tappe=True)
    verifica("contrario: i test dell'agente verdi senza controllo indipendente (un programma "
             "senza esempi): la tappa resta, «senza esempi di accettazione»",
             ris.get("esito") == "tappa" and ris.get("test_passano") is True
             and lav.segnali.get("tappa_no") == "senza esempi di accettazione"
             and not regole(lav).get("agente_consegna_alla_tappa"), f"{ris} {lav.segnali}")
    giusta = [P.scrivi("calcola.py", F.CALCOLA_GIUSTO)]
    rosso = [P.scrivi("test_calcola.py", F.TEST_ROSSO)]
    lav, ris, log = _correzione(tmp, "riprodotta", [giusta, rosso, [P.ESEGUI]])
    verifica("una correzione con il test che riproduce alla tappa: «fatto» con la riproduzione",
             ris.get("esito") == "fatto" and ris.get("consegna_al_tetto") == "tappa"
             and ris.get("consegna_al_tetto_con") == "riproduzione"
             and lav.riproduzione.get("stato") == "riprodotto"
             and regole(lav).get("agente_consegna_alla_tappa") == 1, f"{ris} {log[-3:]}")
    lav, ris, log = _correzione(tmp, "non-riprodotta", [giusta, [P.ESEGUI], [P.LEGGI]])
    verifica("contrario: la correzione senza un test nuovo: la tappa resta, e il rimando della "
             "riproduzione non è consumato (resta per la consegna del giro dopo)",
             ris.get("esito") == "tappa"
             and str(lav.segnali.get("tappa_no")).startswith("correzione non riprodotta")
             and int(lav.riproduzione.get("rimandi", 0)) == 0
             and not regole(lav).get("correzione_rimandata"), f"{ris} {lav.riproduzione}")
    # Revisione della PR #194: il tetto del giro resta nel risultato
    lav, ris, log = _correzione(tmp, "riprodotta-tetto", [giusta, rosso, [P.ESEGUI]])
    verifica("…con «tappa» il risultato tiene anche il tetto del giro (passate)",
             ris.get("consegna_al_tetto") == "tappa"
             and ris.get("consegna_al_tetto_giro") == "passate", str(ris)[:300])
    # Revisione della PR #194: un giro con una nota della persona non si chiude d'ufficio
    sbagliata = [P.scrivi("estensione.py", F2.SBAGLIATA)]
    corretta = [P.scrivi("estensione.py", F2.GIUSTA)]
    lav, ris, log, sb = _estensione(tmp, "nota", [sbagliata, [P.ESEGUI], [F2.LEGGI]])
    verifica("giro 1 con gli esempi rossi: tappa", ris.get("esito") == "tappa"
             and str(lav.segnali.get("tappa_no")).startswith("esempi di accettazione rossi"),
             f"{ris.get('esito')} {lav.segnali.get('tappa_no')}")
    lav.risposta, lav.nota_giro, lav.passi0 = "continua", "aggiungi anche le iarde", lav.passi
    lav, ris, log, sb = _estensione(tmp, "nota", [corretta, [P.ESEGUI], [F2.LEGGI]], lav=lav,
                                    sb=sb)
    verifica("contrario: giro 2 con la nota «aggiungi anche …», al tetto con gli esempi verdi "
             "ma senza averla fatta: resta tappa, il motivo in tappa_no",
             ris.get("esito") == "tappa"
             and lav.segnali.get("tappa_no") == "la persona ha chiesto qualcosa in questo giro"
             and lav.segnali.get("nota_giro") == "aggiungi anche le iarde"
             and not regole(lav).get("agente_consegna_alla_tappa"), f"{ris} {lav.segnali}")
    lav.risposta, lav.passi0 = "continua", lav.passi
    lav, ris, log, sb = _estensione(tmp, "nota", [[F2.LEGGI]] * 3, lav=lav, sb=sb)
    verifica("…il giro dopo senza nota la toglie, e la tappa si chiude «fatto»",
             ris.get("esito") == "fatto" and ris.get("consegna_al_tetto") == "tappa"
             and "nota_giro" not in lav.segnali, f"{ris.get('esito')} {lav.segnali}")
    # Revisione della PR #194: dopo la prosa il no della riproduzione non consuma il rimando
    lav, ris, log = _correzione(tmp, "prosa", [giusta, [P.ESEGUI], "Ho finito.", "Ho finito.",
                                                [P.consegna()], [P.consegna()]],
                                max_passi=8, tappe=False)
    verifica("dopo due passate di prosa la correzione senza test: no («correzione non "
             "riprodotta»), e alla consegna dell'agente il rimando c'è ancora",
             str(lav.segnali.get("prosa_no")).startswith("correzione non riprodotta")
             and regole(lav).get("correzione_rimandata") == 1
             and any("La correzione non è valida" in r for r in P.risultati(lav, "consegna")),
             f"{lav.segnali.get('prosa_no')} {regole(lav)} {ris}")
    # A voce: fuori da uno sviluppo la frase dell'estensione, in uno sviluppo l'annuncio
    from calliope.agenti.ciclo import Lavoro
    from calliope.agenti.servizio import AL_TETTO_TAPPA, Lavori
    s = SimpleNamespace(female=True, in_tappa=Lavori.in_tappa)
    lv = Lavoro("F1", "estensione", "x", titolo="Il tris")
    lv.stato = "fatto"
    lv.risultato = {"esito": "fatto", "estensione": {"frase": "«Il tris» è pronto da provare."},
                    "consegna_al_tetto": "tappa", "consegna_al_tetto_con": "esempi"}
    f = Lavori.frase_finale(s, lv)
    verifica("a voce: «l'agente non ha consegnato, ma ha finito: l'ho chiuso io»",
             f == "«Il tris» è pronto da provare. " + AL_TETTO_TAPPA
             and "non ha consegnato, ma ha finito: l'ho chiuso io" in AL_TETTO_TAPPA, f)
    from calliope.sviluppo import Sviluppi, Sviluppo
    finto = SimpleNamespace(mancanze_dette=lambda sv: "", _frase_ricollaudo=lambda rc: "",
                            e_gioco=lambda sv: True, log=lambda *a: None)
    sv = Sviluppo(id="S1", persona="ada-id", persona_nome="Ada", titolo="Il tris", versione=1,
                  gioco=True)
    lv.persona_nome = "Ada"
    try:
        a = Sviluppi.frase_pronto(finto, sv, lv)
    except Exception as e:  # noqa: BLE001
        a = f"{type(e).__name__}: {e}"
    lv.risultato = dict(lv.risultato, consegna_al_tetto="passate")
    try:
        b = Sviluppi.frase_pronto(finto, sv, lv)
    except Exception as e:  # noqa: BLE001
        b = f"{type(e).__name__}: {e}"
    verifica("in uno sviluppo l'annuncio lo dice; contrario: una consegna al tetto no",
             AL_TETTO_TAPPA in a and AL_TETTO_TAPPA not in b, f"{a} | {b}")


# ═══════════════════════════ 4. il segnaposto ═══════════════════════════

def prova_segnaposto(tmp: Path):
    sezione("4. scrivi_file e modifica_file rifiutano il segnaposto della compattazione")
    from calliope.agenti.ciclo import Lavoro
    from calliope.agenti.contesto_lavoro import ContestoLavoro, PassiMemoria, segnaposto
    from calliope.config import Config
    gc = ContestoLavoro(Config(), 16384, PassiMemoria())
    m = {"role": "assistant", "content": "", "tool_calls": [{"function": {
        "name": "scrivi_file", "arguments": {"percorso": "gioco.test.js",
                                             "contenuto": "x" * 6000}}}]}
    gc._alleggerisci(m)
    vero = m["tool_calls"][0]["function"]["arguments"]["contenuto"]
    verifica("il segnaposto della compattazione si riconosce (la forma vera, dal contesto)",
             segnaposto(vero) == vero and vero.startswith("[6000 caratteri: completo in "), vero)
    ag = G.agente()
    sb = G.sandbox(tmp, "segnaposto")
    sb.scrivi("gioco.test.js", "// i test\n")
    lav = Lavoro("S1", "estensione", "il tris")
    r = ag._strumento(lav, sb, "scrivi_file", {"percorso": "gioco.test.js", "contenuto": vero})
    verifica("scrivi_file con il segnaposto: rifiutato, «rileggi il file con leggi_file», la "
             "regola agente_segnaposto, il file com'era",
             r.get("ok") is False and "leggi_file" in r.get("errore", "")
             and "segnaposto" in r.get("errore", "")
             and regole(lav).get("agente_segnaposto") == 1
             and sb.leggi("gioco.test.js") == "// i test\n", str(r))
    r = ag._strumento(lav, sb, "scrivi_file", {"percorso": "gioco.test.js",
                                               "contenuto": "const a = 1;\n" + vero + "\n"})
    verifica("…anche dentro altro testo", r.get("ok") is False
             and regole(lav).get("agente_segnaposto") == 2, str(r))
    r = ag._strumento(lav, sb, "modifica_file", {"percorso": "gioco.test.js",
                                                 "vecchio": "// i test", "nuovo": vero})
    verifica("modifica_file con il segnaposto nel «nuovo»: rifiutata",
             r.get("ok") is False and "leggi_file" in r.get("errore", "")
             and sb.leggi("gioco.test.js") == "// i test\n", str(r))
    r = ag._strumento(lav, sb, "scrivi_file", {"percorso": "gioco.test.js",
                                               "contenuto": "const v = [6000, 3]; // [6000 "
                                                            "caratteri]\n"})
    verifica("contrario: un testo con le parentesi quadre si scrive", r.get("ok") is True,
             str(r))
    r = ag._strumento(lav, sb, "modifica_file", {"percorso": "gioco.test.js",
                                                 "vecchio": "[6000, 3]", "nuovo": "[1, 2]"})
    verifica("contrario: una modifica vera si fa", r.get("ok") is True
             and "[1, 2]" in sb.leggi("gioco.test.js")
             and regole(lav).get("agente_segnaposto") == 3, str(r))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="calliope-apri-tappa-"))
    os.environ.setdefault("CALLIOPE_CONFIG_LOCALE", str(tmp / "nessuno.yaml"))
    try:
        prova_frase()
        prova_motore_finto(tmp / "finto")
        prova_tappa(tmp / "tappa")
        prova_segnaposto(tmp / "segnaposto")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
