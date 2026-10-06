import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Il PC comandato a voce con il modello vero (Ollama), sempre con il PC FINTO.

Frasi come dette a voce → tool e argomenti giusti, stato del PC finto dopo, risposta e
tempi (prima frase e totale). Dario amministra (quindi è proprietario del portatile),
Bianca è familiare ma non proprietaria (niente file né programmi aperti), più un ospite
che prova ad alzare il volume. In mezzo qualche distrattore (ora, conti, timer) che non
deve finire nei tool pc_*. Una sessione nuova = un Brain nuovo, senza storia.

    python prove\\prova_pc_ollama.py        # 2 giri
    python prove\\prova_pc_ollama.py 1      # 1 giro
"""

import re
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ora_giusta import ora_o_tool  # noqa: E402  (03/10: l'ora giusta senza tool vale)
from calliope.agenda import Agenda
from calliope.brain import Brain
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from prove.pc_finto import FILE, FakePC

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


class Prof:
    def __init__(self, pid, name, admin=False):
        self.id, self.name, self.admin = pid, name, admin


class Speakers:
    def __init__(self):
        self.p = {"Dario": Prof("dario-id", "Dario", True), "Bianca": Prof("bianca-id", "Bianca")}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self, name, level):
        self.current_speaker, self.current_level, self.from_session = name, level, False


cfg = Config()
DONE = re.compile(r"\b(fatto|ho aperto|apro|aperto|ho alzato|alzato|ho trovato|ecco)\b", re.I)


def apri(p):
    return ("apri", p)


def aperti(pc, prima):
    return [a for a in pc.azioni[prima["n"]:] if a[0] in ("apri", "avvia")]


# (sessione, chi, livello, frase, tool atteso o None, controllo(risposta, argomenti, pc, prima))
# `prima` è lo stato del PC finto prima della frase: i controlli sono relativi, così un
# errore non si trascina sulle frasi dopo.
CASI = [
    ("volume", "Dario", "amministra", "Alza un po' il volume del computer.", "pc_volume",
     lambda r, a, pc, p: pc.volume == min(100, p["volume"] + 10)),
    ("volume", "Dario", "amministra", "Abbassa il volume.", "pc_volume",
     lambda r, a, pc, p: pc.volume == max(0, p["volume"] - 10)),
    ("volume", "Dario", "amministra", "Metti il volume a 30.", "pc_volume",
     lambda r, a, pc, p: pc.volume == 30),
    ("volume", "Dario", "amministra", "Alza il volume al massimo.", "pc_volume",
     lambda r, a, pc, p: pc.volume == 100),
    ("volume", "Dario", "amministra", "Togli l'audio.", "pc_volume",
     lambda r, a, pc, p: pc.muto),
    ("volume", "Dario", "amministra", "Riattiva l'audio.", "pc_volume",
     lambda r, a, pc, p: not pc.muto),
    ("musica", "Bianca", "familiare", "Cosa sta suonando sul portatile?", "pc_stato",
     lambda r, a, pc, p: "bohemian" in r.lower()),
    ("musica", "Bianca", "familiare", "Metti in pausa la musica.", "pc_media",
     lambda r, a, pc, p: pc.azioni[-1:] == [("media", "pausa")]),
    ("musica", "Bianca", "familiare", "Passa alla canzone successiva.", "pc_media",
     lambda r, a, pc, p: pc.azioni[-1:] == [("media", "avanti")]),
    ("musica", "Bianca", "familiare", "Fai ripartire la musica.", "pc_media",
     lambda r, a, pc, p: pc.azioni[-1:] == [("media", "riproduci")]),
    ("schermo", "Bianca", "familiare", "Abbassa un po' la luminosità dello schermo.", "pc_luminosita",
     lambda r, a, pc, p: pc.lum == p["lum"] - 10),
    ("schermo", "Bianca", "familiare", "Quanta batteria ha il portatile?", "pc_stato",
     lambda r, a, pc, p: "76" in r),
    ("app", "Bianca", "familiare", "Apri la calcolatrice.", "pc_apri_app",
     lambda r, a, pc, p: aperti(pc, p) == [("avvia", "calc.exe")]),
    ("app", "Bianca", "familiare", "Apri Word.", "pc_apri_app",
     lambda r, a, pc, p: aperti(pc, p) == [("avvia", "winword.exe")]),
    ("app", "Bianca", "familiare", "Apri Photoshop.", None,
     lambda r, a, pc, p: not aperti(pc, p) and not re.search(r"\b(apro|ho aperto)\b", r, re.I)),
    ("file", "Dario", "amministra", "Cerca la bolletta della luce sul computer.", "pc_cerca_file",
     lambda r, a, pc, p: "bollett" in str(a.get("testo", "")).lower() and "agosto" in r.lower()),
    ("file", "Dario", "amministra", "Aprila.", "pc_apri_file",
     lambda r, a, pc, p: aperti(pc, p) == [apri(FILE[0]["percorso"])]),
    ("file2", "Dario", "amministra", "Trova i PDF della settimana scorsa.", "pc_cerca_file",
     lambda r, a, pc, p: a.get("tipo") == "pdf" and "settimana" in str(a.get("periodo", ""))),
    ("file3", "Dario", "amministra", "Cerca le bollette sul computer.", "pc_cerca_file",
     lambda r, a, pc, p: len(re.findall(r"bolletta", r, re.I)) >= 2),
    ("file3", "Dario", "amministra", "Apri la seconda.", "pc_apri_file",
     lambda r, a, pc, p: aperti(pc, p) == [apri(FILE[0]["percorso"])]),
    # 27/09: con il nome detto, apri_file senza ricerca e poi «non so quale file cercare».
    # Va bene aprirlo subito (un solo risultato) o chiedere «lo apro?» dopo averlo trovato.
    ("filenome", "Dario", "amministra", "Aprimi il file preventivo cucina.", "pc_cerca_file",
     lambda r, a, pc, p: aperti(pc, p) == [apri(FILE[3]["percorso"])]
     or ("preventivo" in r.lower() and "?" in r)),
    ("filenome2", "Dario", "amministra", "Apri il file preventivo.", "pc_cerca_file",
     lambda r, a, pc, p: aperti(pc, p) == [apri(FILE[3]["percorso"])]
     or ("preventivo" in r.lower() and "?" in r)),
    ("bianca", "Bianca", "familiare", "Cerca la bolletta della luce sul computer.", None,
     lambda r, a, pc, p: "agosto" not in r.lower() and not aperti(pc, p)
     and not re.search(r"\bho trovato\b", r, re.I)),
    ("bianca", "Bianca", "familiare", "Che programmi sono aperti sul computer?", None,
     lambda r, a, pc, p: "visual studio" not in r.lower() and "edge" not in r.lower()),
    ("dario", "Dario", "amministra", "Che programmi ho aperti sul computer?", "pc_stato",
     lambda r, a, pc, p: "edge" in r.lower()),
    ("ospite", None, "ospite", "Alza il volume del computer.", None,
     lambda r, a, pc, p: pc.volume == p["volume"] and not DONE.search(r)),
    ("distrattori", "Dario", "amministra", "Che ore sono?", "ora_attuale", lambda r, a, pc, p: True),
    ("distrattori", "Dario", "amministra", "Quanto fa 17 per 6?", "calcola",
     lambda r, a, pc, p: "102" in r),
    ("distrattori", "Dario", "amministra", "Metti un timer di 5 minuti.", "timer_imposta",
     lambda r, a, pc, p: True),
    ("blocco", "Bianca", "familiare", "Blocca il computer.", "pc_blocca",
     lambda r, a, pc, p: pc.locked),
    ("blocco", "Bianca", "familiare", "Apri il blocco note.", None,
     lambda r, a, pc, p: not aperti(pc, p) and "blocc" in r.lower()),
]

righe = []
for giro in range(1, GIRI + 1):
    tmp = Path(tempfile.mkdtemp())
    ag = Agenda(str(tmp / "memoria.db"))
    pc = FakePC(volume=40, luminosita=80,
                media={"titolo": "Bohemian Rhapsody", "artista": "Queen", "app": "Spotify",
                       "in_riproduzione": True})
    # Come in Calliope: anche i tool dei documenti (senza servizio: qui non vanno chiamati)
    # Con i tool degli schermi e degli agenti, come in Calliope (schermi accesi di
    # predefinito e agenti con dgx.yaml, 02/10)
    reg = build_registry(pc={"portatile": pc}, documenti=FORMATI, schermi=True, agenti=True)
    brains = {}
    for sessione, chi, livello, frase, atteso, controllo in CASI:
        key = (sessione, chi)
        if key not in brains:
            ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(chi, livello),
                              speaker=None, agenda=ag, pc={"portatile": pc})
            brains[key] = Brain(cfg, reg, ctx)
        b = brains[key]
        prima = {"volume": pc.volume, "muto": pc.muto, "lum": pc.lum, "n": len(pc.azioni)}
        t0 = time.perf_counter()
        primo, parti = None, []
        for pezzo in b.stream_reply(frase, livello):
            if primo is None and pezzo.strip():
                primo = time.perf_counter() - t0
            parti.append(pezzo)
        totale = time.perf_counter() - t0
        risposta = "".join(parti).strip()
        tools = [t["nome"] for t in b.last_tools]
        args = next((t["argomenti"] for t in reversed(b.last_tools) if t["nome"] == atteso), {})
        if atteso is None:
            # Nessun tool obbligato, ma nessun tool pc_* riuscito (rifiuti e catalogo)
            ok_tool = not any(t["nome"].startswith("pc_") and t["ok"] for t in b.last_tools)
        else:
            ok_tool = atteso in tools or ora_o_tool(atteso, tools, risposta)
        try:
            ok_stato = bool(controllo(risposta, args, pc, prima))
        except Exception as e:                      # un controllo rotto è un errore, non un crash
            ok_stato, risposta = False, f"{risposta} [controllo: {e}]"
        ok = ok_tool and ok_stato
        argomenti = "; ".join(f"{t['nome']}({', '.join(f'{k}={v!r}' for k, v in t['argomenti'].items())})"
                              for t in b.last_tools) or "—"
        verifica(f"[{giro}] {chi or 'ospite'}: «{frase}» → {argomenti}", ok,
                 f"{primo or 0:.2f}/{totale:.2f}s  {risposta[:110]!r}")
        righe.append((giro, frase, ok, primo or 0, totale))
        if sessione == "blocco" and frase.startswith("Apri"):
            pc.locked = False

prime = sorted(r[3] for r in righe)
print(f"\nprima frase: mediana {prime[len(prime) // 2]:.2f}s, massimo {prime[-1]:.2f}s; "
      f"riuscite {sum(r[2] for r in righe)}/{len(righe)}")
print(f"{errori} errori" if errori else "Tutto a posto.")
sys.exit(1 if errori else 0)
