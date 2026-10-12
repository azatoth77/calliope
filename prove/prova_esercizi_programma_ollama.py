"""
Fase B dell'indice del programma con il modello vero (12/10/2026 sera): il modello del
profilo ridotto da 8 GB (gemma4:e4b, 4B effettivi) passa per lo strumento? Nomi di fantasia,
data dell'anno scolastico fissata a ottobre, una bambina di terza elementare.

Il copione (frasi come le trascriverebbe Whisper), e per ogni turno l'azione attesa e lo stato
che deve seguire:

1. «facciamo esercizi di addizioni» → inizia, e la domanda «a che punto siete» del codice;
2. «siamo alle addizioni col riporto fino a cento» → a_che_punto (argomento, entro 100,
   riporto true): salvato e mappato sull'indice;
3. una risposta giusta → rispondi;
4. «sono troppo facili, me ne dai di più difficili?» → piu_difficile;
5. «basta così» → fine;
6. «facciamo le frazioni» → inizia, «non ho esercizi adatti» (terza);
7. «sì, voglio provarle lo stesso» → inizia con oltre=true, o la domanda sì/no del codice e
   poi «sì»;
8. «basta» → fine;
9. «simuliamo un'interrogazione sulle addizioni» → interroga;
10. la risposta giusta alla domanda aperta → rispondi; il giudizio con la sicurezza lo dà il
    modello della voce o, se non lo passa, il giudice chiamato dal codice: giusta (o in parte),
    non «da guardare» (anche il conto, se la prima domanda è un esercizio);
11. «basta così» → fine;
12. «interrogami sul capitolo 4 di storia» → senza pagina la chiede (dal tool, o il
    modello da sé: conta che non improvvisi le domande).

Si contano i turni giusti (azione e stato), i turni senza tool e la prima frase. Esce con 1 se
i turni giusti sono meno di `--soglia` (0,75).

    python prove/prova_esercizi_programma_ollama.py [--giri 1] [--url http://127.0.0.1:11434]
        [--modello gemma4:e4b-it-qat] [--num-ctx 16384] [--keep-alive -1m] [--soglia 0.75]
        [--json uscita.json]
"""

import datetime
import json
import statistics
import sys
import tempfile
import time
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from calliope import minori as M  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.esercizi import sessione as SE  # noqa: E402
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
SOGLIA = float(arg("--soglia", "0.75"))
USCITA = arg("--json")
OTTOBRE = datetime.date(2026, 10, 12)
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


# Le risposte giuste, dette da una bambina, alle domande aperte delle addizioni
RISPOSTE_APERTE = {
    "add.riporto": "Si comincia dalle unità, e se fanno più di nove scrivo l'unità e riporto uno "
                   "alle decine.",
    "add.ordine": "No, non cambia, perché l'ordine non conta.",
}


def un_giro(giro: int) -> list[dict]:
    tmp = Path(tempfile.mkdtemp())
    cfg = Config()
    cfg.llm_backend, cfg.llm_native_url, cfg.llm_model = "ollama", URL, MODELLO
    cfg.llm_num_ctx, cfg.llm_keep_alive = NUM_CTX, KEEP
    cfg.llm_profilo = None
    cfg.memory_db = str(tmp / "memoria.db")
    cfg.guardiano_modello = ""
    cfg.esercizi_pronti = 0
    cfg.esercizi_punto_giorni = 14
    reg = Reg([prof("Ada", admin=True), prof("Nina", 8, tutori=["ada-id"])])
    M.prepara(cfg, registry=reg, log=lambda *a: None)
    srv = SE.prepara(cfg, registry=reg, log=lambda *a: None)
    srv._oggi = lambda: OTTOBRE
    tools = build_registry()
    for spec in minori_specs():
        tools.register(spec)
    sc = SpeakerContext(reg)
    sc.current_speaker, sc.identified_by = "Nina", "voce"
    ctx = ToolContext(cfg=cfg, speakers=reg, speaker_ctx=sc, speaker=None)
    b = Brain(cfg, tools, ctx)
    level = sc.current_level
    pid = reg.get("Nina").id
    righe = []

    def turno(frase: str, attesa: str, controllo) -> dict:
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
        argomenti = [x.get("argomenti") if isinstance(x.get("argomenti"), dict) else {}
                     for x in chiamate]
        azioni = [str(a.get("azione", "")) for a in argomenti]
        try:
            ok = bool(controllo(srv.sessione(pid), argomenti, " ".join(detto)))
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"   controllo: {type(e).__name__}: {e}")
        r = {"giro": giro, "frase": frase, "attesa": attesa, "ok": ok, "azioni": azioni,
             "argomenti": argomenti, "tool": [x["nome"] for x in b.last_tools],
             "detto": " ".join(detto), "prima_s": round(prima or tot, 2),
             "totale_s": round(tot, 2), "regole": list(b.rules_fired())}
        righe.append(r)
        print(f"{'ok ' if ok else 'ERR'} [{attesa}] «{frase}» → {r['detto'][:160]}  "
              f"[{', '.join(r['tool']) or 'nessun tool'} {json.dumps(argomenti, ensure_ascii=False)[:160]}] "
              f"{r['prima_s']} s", flush=True)
        return r

    def risposta_giusta(s):
        v = Fraction(s.es.risposta)
        return f"{v.numerator}." if v.denominator == 1 else f"{v.numerator}/{v.denominator}."

    print(f"\n── giro {giro} ({MODELLO}) ──", flush=True)
    turno("Calliope, facciamo un po' di esercizi di addizioni?", "inizia + a che punto",
          lambda s, a, d: s is not None and s.attesa_punto == "inizio")
    turno("Siamo alle addizioni col riporto, fino a cento.", "a_che_punto",
          lambda s, a, d: (srv.registro.punto(pid, "matematica") or {}).get("dati", {}).get(
              "entro") == 100 and s is not None and s.es is not None)
    punto = (srv.registro.punto(pid, "matematica") or {}).get("dati", {})
    righe[-1]["punto"] = punto
    s = srv.sessione(pid)
    if s is not None and s.es is not None:
        firma = s.es.firma
        turno(risposta_giusta(s), "rispondi",
              lambda s, a, d: s is not None and s.es is not None and s.es.firma != firma)
    turno("Sono troppo facili, me ne dai di più difficili?", "piu_difficile",
          lambda s, a, d: "piu_difficile" in [x.get("azione") for x in a])
    turno("Basta così, grazie.", "fine", lambda s, a, d: s is None)
    turno("Facciamo le frazioni.", "fuori programma",
          lambda s, a, d: s is None and "non ho esercizi adatti" in d.lower())
    r = turno("Sì, voglio provarle lo stesso.", "oltre (o la domanda sì/no)",
              lambda s, a, d: (s is not None and s.argomento == "frazioni" and s.oltre)
              or "vuoi provare le frazioni" in d.lower())
    if srv.sessione(pid) is None and "vuoi provare" in r["detto"].lower():
        turno("Sì.", "sì alla domanda: oltre",
              lambda s, a, d: s is not None and s.argomento == "frazioni" and s.oltre)
    turno("Basta.", "fine", lambda s, a, d: s is None)
    turno("Simuliamo un'interrogazione sulle addizioni.", "interroga",
          lambda s, a, d: s is not None and s.interroga is not None)
    s = srv.sessione(pid)
    for _ in range(2):
        if s is None or s.es is None:
            break
        if s.es.tipo == "aperta":
            fatte = len(srv.registro.tentativi(pid, OGGI, OGGI))
            turno(RISPOSTE_APERTE.get(s.es.dati.get("id"), "Non lo so."),
                  "aperta: giudicata giusta",
                  lambda s, a, d: len(srv.registro.tentativi(pid, OGGI, OGGI)) > fatte
                  and srv.registro.tentativi(pid, OGGI, OGGI)[-1]["esito"] in (
                      "giusta", "parziale"))
        else:
            firma = s.es.firma
            turno(risposta_giusta(s), "rispondi (interrogazione)",
                  lambda s, a, d: s is None or s.es is None or s.es.firma != firma)
        s = srv.sessione(pid)
    turno("Basta così.", "fine", lambda s, a, d: s is None)
    turno("Interrogami sul capitolo 4 di storia.", "serve la pagina",
          lambda s, a, d: s is None and any(x in d.lower() for x in ("pagina", "testo", "foto")))
    return righe


def main() -> int:
    righe = []
    for g in range(1, GIRI + 1):
        righe.extend(un_giro(g))
    turni = [r for r in righe if "attesa" in r]
    giusti = sum(r["ok"] for r in turni)
    senza = sum(1 for r in turni if not r["tool"])
    prime = [r["prima_s"] for r in turni]
    print(f"\nTurni giusti: {giusti}/{len(turni)} ({giusti / max(1, len(turni)):.0%}); senza "
          f"tool: {senza}; prima frase mediana {statistics.median(prime):.2f} s, massima "
          f"{max(prime):.2f} s")
    for att in dict.fromkeys(r["attesa"] for r in turni):
        rr = [r for r in turni if r["attesa"] == att]
        print(f"  {att}: {sum(r['ok'] for r in rr)}/{len(rr)}")
    if USCITA:
        Path(USCITA).write_text(json.dumps(righe, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    return 0 if giusti >= SOGLIA * len(turni) else 1


if __name__ == "__main__":
    sys.exit(main())
