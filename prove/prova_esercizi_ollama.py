"""
Esercizi a voce con il modello vero (08/10/2026, calliope/esercizi/, docs/ricerche/
2026-10-08-esercizi.md § 7).

Per materia una sessione di 10 esercizi con le frasi di un ragazzo simulate come le
trascriverebbe Whisper: risposte giuste (in cifre o in lettere), sbagliate, «dammi un
indizio», «secondo me è sbagliato», alla fine «basta così». Il modello deve passare ogni frase
al tool `esercizi` con l'azione giusta: la correzione la fa il codice. Si contano:

- turni giusti: dopo il turno lo stato della sessione è quello atteso (giusta → esercizio
  nuovo; sbagliata → stesso esercizio, un errore in più; indizio → nessun errore in più;
  segnalazione registrata; fine → sessione chiusa);
- tool chiamato con l'azione attesa, turni senza tool, prima frase (mediana, p90);
- il secondo parere vero sugli esercizi d'italiano (stesso modello: accordo e tempi).

    python prove/prova_esercizi_ollama.py [--giri 1] [--url http://127.0.0.1:11434]
        [--modello gemma4:e4b-it-qat] [--num-ctx 16384] [--keep-alive -1m]
        [--materie matematica,italiano] [--json uscita.json]
"""

import datetime
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from calliope import minori as M  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.esercizi import sessione as SE  # noqa: E402
from calliope.esercizi.numeri import frazione_detta, in_lettere  # noqa: E402
from calliope.speaker_id import SpeakerContext, UserProfile, name_key  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.minori import minori_specs  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402
from calliope.tts import clean_for_speech, split_sentences  # noqa: E402


def arg(nome, predefinito=None):
    if nome in sys.argv:
        return sys.argv[sys.argv.index(nome) + 1]
    return predefinito


GIRI = int(arg("--giri", "1"))
URL = arg("--url", "http://127.0.0.1:11434")
MODELLO = arg("--modello", "gemma4:e4b-it-qat")
NUM_CTX = int(arg("--num-ctx", "16384"))
KEEP = arg("--keep-alive", "-1m")
MATERIE = arg("--materie", "matematica,italiano").split(",")
USCITA = arg("--json")
OGGI = datetime.date.today()


def nato(anni):
    d = OGGI - datetime.timedelta(days=40)
    return d.replace(year=d.year - anni).isoformat()


class Reg:
    def __init__(self, profili):
        self.cfg = Config()
        self.users = {p.name: p for p in profili}

    def get(self, n):
        return self.users.get(n)

    def find(self, n):
        k = name_key(n)
        return next((x for x in self.users if name_key(x) == k), None)

    def save(self):
        pass

    def known_speakers(self):
        return list(self.users)


def prof(nome, anni=None, admin=False, gender="f", tutori=()):
    p = UserProfile(nome, admin=admin, gender=gender, nascita=nato(anni) if anni else None,
                    tutori=list(tutori))
    p.id = nome.lower() + "-id"
    return p


# Il copione di 10 esercizi: per ogni esercizio le mosse del ragazzo
COPIONE = [["giusta"], ["giusta_lettere"], ["sbagliata", "aiuto", "giusta"], ["giusta"],
           ["segnala", "giusta"], ["giusta_lettere"], ["sbagliata", "sbagliata", "giusta"],
           ["giusta"], ["aiuto", "giusta_lettere"], ["giusta"]]
INIZIO = {"matematica": ("Bianca", "Calliope, facciamo un po' di esercizi di frazioni?"),
          "italiano": ("Luca", "Mi fai fare qualche esercizio di analisi grammaticale?")}


def detta(es, mossa: str, n: int) -> str:
    """La frase del ragazzo come la trascriverebbe Whisper."""
    if mossa == "aiuto":
        return ("Non lo so, mi dai un indizio?", "Mi aiuti? Dammi un suggerimento.")[n % 2]
    if mossa == "segnala":
        return "Secondo me questo esercizio è sbagliato."
    if es.materia == "matematica":
        from fractions import Fraction
        v = Fraction(es.risposta)
        if mossa == "sbagliata":
            v = v + (1 if n % 2 else 2)
        if mossa == "giusta_lettere" or (mossa == "sbagliata" and n % 2):
            parole = frazione_detta(v)
            if v.denominator == 1:
                parole = in_lettere(int(v))
            return ("Fa " + parole + ".", parole.capitalize() + ".")[n % 2]
        s = f"{v.numerator}/{v.denominator}" if v.denominator > 1 else str(v.numerator)
        return ("Fa " + s + ".", s + ".", "Credo " + s + ".")[n % 3]
    # italiano
    giusta = es.risposta_detta
    if mossa == "sbagliata":
        from calliope.esercizi.italiano import PARTI
        giusta = next(p for p in PARTI if p != es.risposta and p != "interiezione")
    if es.argomento == "analisi_grammaticale":
        art = "un'" if giusta[0] in "aei" else "una " if giusta in ("preposizione", "congiunzione") else "un "
        return (f"È {art}{giusta}.", f"{giusta.capitalize()}.")[n % 2]
    return f"{giusta.capitalize()}."


def una_sessione(materia: str, giro: int) -> list[dict]:
    tmp = Path(tempfile.mkdtemp())
    cfg = Config()
    cfg.llm_backend, cfg.llm_native_url, cfg.llm_model = "ollama", URL, MODELLO
    cfg.llm_num_ctx, cfg.llm_keep_alive = NUM_CTX, KEEP
    cfg.llm_profilo = None
    cfg.memory_db = str(tmp / "memoria.db")
    cfg.guardiano_modello = ""
    dario, elena = prof("Dario", admin=True, gender="m"), prof("Elena")
    reg = Reg([dario, elena, prof("Bianca", 9, tutori=["dario-id", "elena-id"]),
               prof("Luca", 12, gender="m", tutori=["elena-id"])])
    M.prepara(cfg, registry=reg, log=lambda *a: None)
    srv = SE.prepara(cfg, registry=reg, log=lambda *a: print(*a, flush=True))
    tools = build_registry()
    for spec in minori_specs():
        tools.register(spec)
    chi, prima_frase = INIZIO[materia]
    sc = SpeakerContext(reg)
    sc.current_speaker, sc.identified_by = chi, "voce"
    ctx = ToolContext(cfg=cfg, speakers=reg, speaker_ctx=sc, speaker=None)
    b = Brain(cfg, tools, ctx)
    level = sc.current_level
    pid = reg.get(chi).id
    righe = []

    def turno(frase: str, attesa: str, controllo) -> dict:
        s0 = srv.sessione(pid)
        stato0 = (s0.es.firma if s0 and s0.es else None, s0.errori if s0 else 0,
                  s0.aiuti if s0 else 0, len(srv.registro.segnalazioni(pid)))
        t0 = time.perf_counter()
        prima, detto = None, []
        for s in split_sentences(b.stream_reply(frase, level)):
            s = clean_for_speech(b.strip_tool_mentions(s))
            if not s:
                continue
            if prima is None:
                prima = time.perf_counter() - t0
            detto.append(s)
        tot = time.perf_counter() - t0
        chiamate = [x for x in b.last_tools if x["nome"] == "esercizi"]
        azioni = [str((x.get("argomenti") if isinstance(x.get("argomenti"), dict) else {})
                      .get("azione", "")) for x in chiamate]
        ok = bool(controllo(stato0, srv.sessione(pid), srv))
        r = {"giro": giro, "materia": materia, "frase": frase, "attesa": attesa, "ok": ok,
             "azioni": azioni, "tool": [x["nome"] for x in b.last_tools],
             "detto": " ".join(detto), "prima_s": round(prima or tot, 2), "totale_s": round(tot, 2),
             "regole": list(b.rules_fired())}
        righe.append(r)
        print(f"{'ok ' if ok else 'ERR'} [{attesa}] «{frase}» → {r['detto'][:150]}  "
              f"[{', '.join(r['tool']) or 'nessun tool'} {','.join(azioni)}] {r['prima_s']} s",
              flush=True)
        return r

    print(f"\n── {materia}, {chi} ({MODELLO}), giro {giro} ──", flush=True)
    t0 = time.perf_counter()
    turno(prima_frase, "inizia", lambda s0, s, v: s is not None and s.es is not None)
    if srv.sessione(pid) is None:
        return righe
    n = 0
    for mosse in COPIONE:
        for mossa in mosse:
            s = srv.sessione(pid)
            if s is None or s.es is None:
                break
            frase = detta(s.es, mossa, n)
            n += 1
            if mossa.startswith("giusta"):
                ctrl = (lambda s0, s, v: s is None or (s.es is not None and s.es.firma != s0[0]))
            elif mossa == "sbagliata":
                ctrl = (lambda s0, s, v: s is not None and s.es.firma == s0[0]
                        and s.errori == s0[1] + 1)
            elif mossa == "aiuto":
                ctrl = (lambda s0, s, v: s is not None and s.es.firma == s0[0]
                        and s.errori == s0[1] and s.aiuti == s0[2] + 1)
            else:
                ctrl = (lambda s0, s, v: len(v.registro.segnalazioni(pid)) == s0[3] + 1)
            r = turno(frase, mossa, ctrl)
            if mossa == "segnala" and r["ok"]:
                # Dopo la segnalazione l'esercizio può essere stato tolto: si va avanti
                pass
    turno("Basta così, grazie.", "fine", lambda s0, s, v: s is None)
    sec = time.perf_counter() - t0
    righe.append({"giro": giro, "materia": materia, "riassunto": True, "secondi": round(sec, 1),
                  "banco": srv.registro.banco_conta(),
                  "parere_ms": srv.parere.ultimo_ms if materia == "italiano" else None})
    return righe


def main():
    tutte = []
    for g in range(1, GIRI + 1):
        for m in MATERIE:
            tutte += una_sessione(m, g)
    turni = [r for r in tutte if not r.get("riassunto")]
    print("\nRiassunto:")
    for m in MATERIE:
        sel = [r for r in turni if r["materia"] == m]
        if not sel:
            continue
        ok = sum(r["ok"] for r in sel)
        senza = sum(1 for r in sel if "esercizi" not in r["tool"])
        ps = sorted(r["prima_s"] for r in sel)
        print(f"   {m}: {ok}/{len(sel)} turni giusti, {senza} senza il tool esercizi, prima "
              f"frase mediana {statistics.median(ps):.2f} s, p90 "
              f"{ps[max(0, int(len(ps) * 0.9) - 1)]:.2f} s")
        for r in sel:
            if not r["ok"]:
                print(f"      ERR [{r['attesa']}] «{r['frase']}» → {r['azioni']} {r['detto'][:100]}")
    for r in tutte:
        if r.get("riassunto"):
            print(f"   {r['materia']} (giro {r['giro']}): {r['secondi']} s in tutto, banco "
                  f"{r['banco']}, ultimo secondo parere {r['parere_ms']} ms")
    tot = sum(r["ok"] for r in turni)
    print(f"\n{tot}/{len(turni)} turni giusti")
    if USCITA:
        Path(USCITA).write_text(json.dumps(tutte, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    sys.exit(0 if tot == len(turni) else 1)


if __name__ == "__main__":
    main()
