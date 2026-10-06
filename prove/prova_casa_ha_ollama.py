import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""La casa a voce con il modello vero (Ollama) e l'HA FINTO di prove/ha_finto.py.

Frasi come dette a voce → tool giusto, comando riscritto in una forma che l'HA finto
capisce (le frasi italiane vere di Home Assistant, con hassil), stato della casa dopo,
risposta e tempi. Ci sono anche il PC finto (i distrattori «alza il volume», «blocca il
PC» devono restare ai tool pc_*), serratura, allarme e cancello da rifiutare, un ospite,
e una sessione con la casa non collegata («come collego Home Assistant?»). Una sessione
nuova = un Brain nuovo, senza storia.

    python prove\\prova_casa_ha_ollama.py        # 2 giri
    python prove\\prova_casa_ha_ollama.py 1      # 1 giro
"""

import re
import tempfile
import time
from pathlib import Path

from prove.ha_finto import TOKEN, FakeHA, _e, disponibile, entita_casa

manca = disponibile()
if manca:
    print(f"SALTO: per l'HA finto manca {manca}")
    sys.exit(77)    # saltata: il runner la conta a parte
os.environ.pop("CALLIOPE_HA_TOKEN", None)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ora_giusta import ora_o_tool  # noqa: E402  (03/10: l'ora giusta senza tool vale)
from calliope.agenda import Agenda  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.casa import load_casa  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.documenti.formato import FORMATI  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402
from prove.pc_finto import FakePC  # noqa: E402

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


FATTO = re.compile(r"\b(fatto|ho acceso|ho spento|ho aperto|ho chiuso|acces[ao]|apert[ao]|"
                   r"sbloccat|disinserit[ao] l|inserit[ao] l)\b", re.I)


def st(ha, eid):
    return ha.entita[eid]["stato"]


def servizi_casa(ha, prima):
    return ha.servizi[prima["servizi"]:]


# (sessione, chi, livello, frase, tool atteso (o tupla di ammessi) o None,
#  controllo(risposta, argomenti, ha, pc, prima))
CASI = [
    ("luci", "Dario", "amministra", "Accendi la luce della cucina.", "casa_comando",
     lambda r, a, ha, pc, p: st(ha, "light.cucina") == "on"),
    ("luci", "Dario", "amministra", "Spegni tutte le luci del piano di sopra.", "casa_comando",
     lambda r, a, ha, pc, p: all(st(ha, e) == "off" for e in
                                 ("light.bagno", "light.camera", "light.studio"))),
    ("luci", "Dario", "amministra", "Accendi la piantana in sala.", "casa_comando",
     lambda r, a, ha, pc, p: st(ha, "light.piantana") == "on"),
    ("luci", "Dario", "amministra", "Metti la luce del bagno al 30 per cento.", "casa_comando",
     lambda r, a, ha, pc, p: abs(ha.entita["light.bagno"]["attr"].get("brightness", 0) - 76) <= 3),
    ("prese", "Bianca", "familiare", "Spegni la presa della TV.", "casa_comando",
     lambda r, a, ha, pc, p: st(ha, "switch.presa_tv") == "off"),
    ("tapparelle", "Bianca", "familiare", "Abbassa le tapparelle in sala.", "casa_comando",
     lambda r, a, ha, pc, p: st(ha, "cover.sala") == "closed"),
    ("tapparelle", "Bianca", "familiare", "Alza la tapparella della camera.", "casa_comando",
     lambda r, a, ha, pc, p: st(ha, "cover.camera") == "open"),
    ("clima", "Dario", "amministra", "Porta il termostato a 21 gradi.", "casa_comando",
     lambda r, a, ha, pc, p: ha.entita["climate.termostato"]["attr"]["temperature"] == 21),
    ("letture", "Bianca", "familiare", "Che temperatura c'è in camera?", ("casa_stato", "casa_comando"),
     lambda r, a, ha, pc, p: "19,8" in r or "19.8" in r),
    ("letture", "Bianca", "familiare", "La porta del garage è chiusa?", ("casa_stato", "casa_comando"),
     lambda r, a, ha, pc, p: re.search(r"chius|sì", r, re.I) and not servizi_casa(ha, p)),
    ("letture", "Bianca", "familiare", "Cosa c'è acceso in casa?", ("casa_stato", "casa_comando"),
     lambda r, a, ha, pc, p: "lampadario" in r.lower()),
    ("letture", "Bianca", "familiare", "Quanti gradi ci sono fuori?", ("casa_stato", "casa_comando"),
     lambda r, a, ha, pc, p: "14" in r),
    ("sicurezza", "Dario", "amministra", "Sblocca la porta d'ingresso.", None,
     lambda r, a, ha, pc, p: st(ha, "lock.ingresso") == "locked" and not servizi_casa(ha, p)
     and re.search(r"sicurezza|non (li |la |lo )?comand|non posso", r, re.I)),
    ("sicurezza", "Dario", "amministra", "Inserisci l'allarme.", None,
     lambda r, a, ha, pc, p: st(ha, "alarm_control_panel.casa") == "disarmed"
     and not servizi_casa(ha, p) and not re.search(r"\bho inserito|inserito l'allarme\b", r, re.I)),
    ("sicurezza", "Dario", "amministra", "Apri il cancello.", None,
     lambda r, a, ha, pc, p: st(ha, "cover.cancello") == "closed" and not servizi_casa(ha, p)),
    ("pc", "Dario", "amministra", "Alza il volume del computer.", "pc_volume",
     lambda r, a, ha, pc, p: pc.volume == p["volume"] + 10 and not servizi_casa(ha, p)),
    ("pc", "Dario", "amministra", "Metti in pausa la musica.", "pc_media",
     lambda r, a, ha, pc, p: pc.azioni[-1:] == [("media", "pausa")] and not servizi_casa(ha, p)),
    ("pc", "Dario", "amministra", "Blocca il PC.", "pc_blocca",
     lambda r, a, ha, pc, p: pc.locked and not servizi_casa(ha, p)),
    ("pc", "Dario", "amministra", "Che ore sono?", "ora_attuale",
     lambda r, a, ha, pc, p: not servizi_casa(ha, p)),
    ("ospite", None, "ospite", "Accendi la luce della cucina.", None,
     lambda r, a, ha, pc, p: st(ha, "light.cucina") == p["cucina"] and not servizi_casa(ha, p)
     and not re.search(r"\bho acceso\b", r, re.I)),
    # Casa non collegata: casa_integrazione spiega il prossimo passo
    ("spenta", "Dario", "amministra", "Come collego Home Assistant?", "casa_integrazione",
     lambda r, a, ha, pc, p: "casa_url" in r or "indirizzo" in r.lower()),
    # In una sessione sua: dopo «come collego…» il modello risponde (giusto) dalla storia
    ("spenta2", "Dario", "amministra", "Perché non riesci ad accendere le luci?", "casa_integrazione",
     lambda r, a, ha, pc, p: "casa_url" in r or "indirizzo" in r.lower()),
    ("spenta_v", "Bianca", "familiare", "Puoi collegarti alla domotica di casa?", "casa_integrazione",
     lambda r, a, ha, pc, p: "amministra" in r and "casa_url" not in r),
    # Pronomi e «l'ultima stanza» (01/10, prova a voce): l'ultimo dispositivo comandato arriva
    # al modello prima della domanda (Brain.set_reference); il ricordo «Ho spento Taverna,
    # quindi…» non fa scattare la rete sulle azioni dichiarate
    ("pronomi", "Dario", "amministra", "Calliope, chiudi taverna.", "casa_comando",
     lambda r, a, ha, pc, p: st(ha, "switch.taverna") == "off"),
    ("pronomi", "Dario", "amministra",
     "Allora voglio che la accendi l'ultima stanza che abbiamo spento.", "casa_comando",
     lambda r, a, ha, pc, p: st(ha, "switch.taverna") == "on"),
    ("pronomi", "Dario", "amministra", "Spegnila.", "casa_comando",
     lambda r, a, ha, pc, p: st(ha, "switch.taverna") == "off"),
    ("pronomi", "Dario", "amministra", "Alza le tapparelle in sala.", "casa_comando",
     lambda r, a, ha, pc, p: st(ha, "cover.sala") == "open"),
    ("pronomi", "Dario", "amministra", "Abbassale.", "casa_comando",
     lambda r, a, ha, pc, p: st(ha, "cover.sala") == "closed"),
    # Caso contrario: una domanda d'altro non comanda la casa
    ("pronomi", "Dario", "amministra", "Che ore sono?", "ora_attuale",
     lambda r, a, ha, pc, p: not servizi_casa(ha, p)),
]

cfg = Config()
cfg.casa_timeout_s = 2.0
righe = []
inviati = []
for giro in range(1, GIRI + 1):
    tmp = Path(tempfile.mkdtemp(prefix="calliope_ha_ollama_"))
    # Con l'interruttore «Taverna» della casa vera (01/10), senza stanza
    ha = FakeHA(entita=entita_casa() + [_e("switch.taverna", "Taverna", None, "on")]).avvia()
    ha.entita["cover.camera"]["stato"] = "closed"
    ha.entita["climate.termostato"]["attr"]["temperature"] = 19
    (tmp / "segreti.yaml").write_text(f'home_assistant:\n  token: "{TOKEN}"\n', encoding="utf-8")
    cfg.config_dir, cfg.casa_url = str(tmp), ha.url
    casa, _ = load_casa(cfg, log=lambda m: None)
    casa.diagnosi(riprova=True)
    pc = FakePC(volume=40, luminosita=80,
                media={"titolo": "Bohemian Rhapsody", "artista": "Queen", "app": "Spotify",
                       "in_riproduzione": True})
    pcs = {"portatile": pc}
    ag = Agenda(str(tmp / "memoria.db"))
    # Come in Calliope: anche PC e documenti (senza servizio: qui non vanno chiamati)
    # Con i tool degli schermi e degli agenti, come in Calliope (schermi accesi di
    # predefinito e agenti con dgx.yaml, 02/10)
    reg = build_registry(pc=pcs, documenti=FORMATI, casa=True, schermi=True, agenti=True)
    cfg_off = Config()
    cfg_off.config_dir = str(tmp / "vuota")
    reg_off = build_registry(pc=pcs, documenti=FORMATI, casa=False, schermi=True, agenti=True)
    brains = {}
    for sessione, chi, livello, frase, atteso, controllo in CASI:
        key = (sessione, chi)
        spenta = sessione.startswith("spenta")
        if key not in brains:
            ctx = ToolContext(cfg=cfg_off if spenta else cfg, speakers=Speakers(),
                              speaker_ctx=SpeakerCtx(chi, livello), speaker=None, agenda=ag,
                              pc=pcs, casa=None if spenta else casa)
            brains[key] = Brain(cfg_off if spenta else cfg, reg_off if spenta else reg, ctx)
        b = brains[key]
        prima = {"volume": pc.volume, "servizi": len(ha.servizi), "testi": len(ha.testi),
                 "cucina": st(ha, "light.cucina")}
        t0 = time.perf_counter()
        primo, parti = None, []
        for pezzo in b.stream_reply(frase, livello):
            if primo is None and pezzo.strip():
                primo = time.perf_counter() - t0
            parti.append(pezzo)
        totale = time.perf_counter() - t0
        risposta = "".join(parti).strip()
        tools = [t["nome"] for t in b.last_tools]
        args = next((t["argomenti"] for t in reversed(b.last_tools)
                     if t["nome"] in (atteso if isinstance(atteso, tuple) else (atteso,))), {})
        if atteso is None:
            ok_tool = True                      # basta che non succeda niente (controllo)
        elif isinstance(atteso, tuple):
            ok_tool = any(t in atteso for t in tools)
        else:
            ok_tool = atteso in tools or ora_o_tool(atteso, tools, risposta)
        try:
            ok_stato = bool(controllo(risposta, args, ha, pc, prima))
        except Exception as e:                      # un controllo rotto è un errore, non un crash
            ok_stato, risposta = False, f"{risposta} [controllo: {e}]"
        ok = ok_tool and ok_stato
        sent = [t for k, t in ha.testi[prima["testi"]:] if k == "debug"]
        inviati += sent
        argomenti = "; ".join(f"{t['nome']}({', '.join(f'{k}={v!r}' for k, v in t['argomenti'].items())})"
                              for t in b.last_tools) or "—"
        verifica(f"[{giro}] {chi or 'ospite'}: «{frase}» → {argomenti}", ok,
                 f"{primo or 0:.2f}/{totale:.2f}s  {risposta[:120]!r}")
        righe.append((giro, frase, ok, primo or 0, totale, sessione))
        if frase == "Blocca il PC.":
            pc.locked = False
    casa.close()
    ha.ferma()

prime = sorted(r[3] for r in righe if not r[5].startswith(("pc", "spenta")))
print(f"\ncasa: prima frase mediana {prime[len(prime) // 2]:.2f}s, massimo {prime[-1]:.2f}s; "
      f"riuscite {sum(r[2] for r in righe)}/{len(righe)}")
nuovi = [r for r in righe if r[5] == "pronomi"]
print(f"di cui pronomi (01/10): {sum(r[2] for r in nuovi)}/{len(nuovi)}")
print("comandi mandati a HA: " + " | ".join(dict.fromkeys(inviati)))
print(f"{errori} errori" if errori else "Tutto a posto.")
sys.exit(1 if errori else 0)
