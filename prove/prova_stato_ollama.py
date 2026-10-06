import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Stato e installazioni a voce con il modello vero (Ollama) e un server HTTP FINTO.

Frasi come dette a voce: «cosa sai fare?», «cosa manca?», «perché non riesci a cercare su
Wikipedia?» (calliope_stato, per livello); «scarica Wikiquote» → proposta → «sì» → avvio;
«scarica la biblioteca» → «no»; un familiare che chiede di installare → rifiuto; «a che
punto è?» e «annulla il download»; capacità che non ci sono («manda un'email»). Niente
internet: il catalogo punta al server finto (prove/http_finto.py), i file sono piccoli e
finiscono in una cartella temporanea. Una sessione = un Brain, con la sua storia.

    python prove\\prova_stato_ollama.py        # 2 giri
    python prove\\prova_stato_ollama.py 1      # 1 giro
"""

import re
import tempfile
import time
from pathlib import Path

from calliope import capacita
from calliope.brain import Brain
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.installa import Installazioni
from calliope.installa.catalogo import FONTI
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from prove.http_finto import FakeHTTP
from prove.pc_finto import FakePC

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
    def __init__(self, name, level, how="voce"):
        self.current_speaker, self.current_level, self.from_session = name, level, False
        self.identified_by = how


def registro_finto() -> capacita.Registro:
    """Come su un portatile senza biblioteca e senza casa: stati fissi, prova ripetibile."""
    reg = capacita.Registro()
    for nome in ("llm", "stt", "voce", "wake", "chi_parla", "audio", "memoria", "pc",
                 "documenti"):
        reg.segnala(nome, "attiva")
    reg.segnala("biblioteca", "mancante", "mancano i file di Wikipedia",
                "Posso scaricarla io: dimmi «scarica la biblioteca», sono circa 12 gigabyte.")
    reg.segnala("casa", "da_configurare", "manca casa_url",
                "Nel file calliope.locale.yaml, sezione casa, scrivi casa_url.")
    # Come al primo avvio dopo il 02/10: server delle schede acceso, nessuno schermo abbinato
    reg.segnala("schermi", "da_configurare", "nessuno schermo abbinato",
                "Apri http://127.0.0.1:8770 sul browser di questo computer e dimmi il codice "
                "che compare: «abbina lo schermo 123456 al soggiorno».")
    return reg


def scaricato(tmp, prefisso):
    return any((tmp / "biblioteca").glob(f"{prefisso}_*.zim"))


NIENTE = re.compile(r"\b(ho (cominciato|iniziato) a scaricare|sto scaricando|scaricat[oa])\b", re.I)

# (sessione, chi, livello, come (voce/breve), frase, tool atteso (o tupla, o None = nessuno
# di quelli d'installazione), controllo(risposta, tmp, srv, inst))
CASI = [
    ("stato_a", "Dario", "amministra", "voce", "Cosa sai fare?", "calliope_stato",
     lambda r, t, s, i: r.startswith("Posso")),
    # Dopo «cosa sai fare?» può rispondere dalla storia (il risultato del tool è lì): va bene,
    # purché dica cosa manca davvero
    ("stato_a", "Dario", "amministra", "voce", "E cosa manca?", ("calliope_stato", None),
     lambda r, t, s, i: "biblioteca" in r.lower()),
    ("stato_b", "Dario", "amministra", "voce", "Perché non riesci a cercare su Wikipedia?",
     "calliope_stato", lambda r, t, s, i: "biblioteca" in r.lower() and "scarica" in r.lower()),
    ("stato_v", "Bianca", "familiare", "voce", "Cosa manca in questa installazione?",
     "calliope_stato", lambda r, t, s, i: "chiedi a chi amministra" in r and "casa_url" not in r),
    ("stato_o", None, "ospite", "voce", "Cosa sai fare?", "calliope_stato",
     lambda r, t, s, i: r.startswith("Puoi chiedermi")),
    ("limiti", "Dario", "amministra", "voce", "Puoi mandare un'email a Marco?", None,
     lambda r, t, s, i: re.search(r"non (posso|riesco|so)|non è possibile", r, re.I)),
    ("limiti", "Dario", "amministra", "voce", "Cercami su internet le notizie di oggi.", None,
     lambda r, t, s, i: re.search(r"non (posso|riesco|ho|so)|internet", r, re.I)),
    # Installazione: proposta, «sì», avvio
    ("quote", "Dario", "amministra", "voce", "Scarica Wikiquote.", "installa_proponi",
     lambda r, t, s, i: r.rstrip().endswith("?") and "megabyte" in r
     and not scaricato(t, "wikiquote_it_all_nopic")),
    # Dal 03/10 un «sì» breve non vale come chi amministra (prova_sicurezza, S6): la
    # conferma è una frase in cui la voce si riconosce
    ("quote", "Dario", "amministra", "voce", "Sì, procedi pure.", "installa_avvia",
     lambda r, t, s, i: "cominciato" in r),
    # Proposta e «no»
    ("bib", "Dario", "amministra", "voce", "Scarica la biblioteca.", "installa_proponi",
     lambda r, t, s, i: r.rstrip().endswith("?") and not scaricato(t, "wikipedia_it_all_mini")),
    ("bib", "Dario", "amministra", "breve", "No, lascia stare.", None,
     lambda r, t, s, i: not i.occupato() and not scaricato(t, "wikipedia_it_all_mini")
     and not NIENTE.search(r)),
    # Un familiare non installa
    ("fam", "Bianca", "familiare", "voce", "Scarica la biblioteca, per favore.",
     ("installa_proponi", None),
     lambda r, t, s, i: "bianca-id" not in i._offerte and not i.occupato()
     and not NIENTE.search(r)),
    # Qualunque tool: anche un installa_avvia scritto come testo è rifiutato dal codice
    ("fam", "Bianca", "familiare", "breve", "Sì, scaricala.", "qualsiasi",
     lambda r, t, s, i: not i.occupato() and not scaricato(t, "wikipedia_it_all_mini")),
    # Lento: a che punto è, poi annulla
    ("lento", "Dario", "amministra", "voce", "Scarica i libri di Gutenberg.", "installa_proponi",
     lambda r, t, s, i: r.rstrip().endswith("?")),
    ("lento", "Dario", "amministra", "voce", "Sì, vai pure.", "installa_avvia",
     lambda r, t, s, i: i.occupato()),
    ("lento", "Dario", "amministra", "voce", "A che punto è il download?", "installa_gestisci",
     lambda r, t, s, i: "per cento" in r or "Sto scaricando" in r),
    ("lento", "Dario", "amministra", "voce", "Annulla il download.", "installa_gestisci",
     lambda r, t, s, i: not i.occupato() and "annullato" in r.lower()),
]
INSTALLA = {"installa_proponi", "installa_avvia", "installa_gestisci"}


def dati(n, seme):
    return (seme.encode() * (n // len(seme) + 1))[:n]


righe = []
for giro in range(1, GIRI + 1):
    tmp = Path(tempfile.mkdtemp(prefix="calliope_stato_ollama_"))
    srv = FakeHTTP().avvia()
    for f in FONTI:
        size = 400_000 if f.prefisso == "gutenberg_it_all" else 3000
        srv.zim(f.cartella, f"{f.prefisso}_2026-09.zim", dati(size, f.prefisso[:6]))
    srv.lento["/zim/gutenberg/gutenberg_it_all_2026-09.zim"] = 0.05
    cfg = Config()
    for f in FONTI:
        if f.attr:
            setattr(cfg, f.attr, str(tmp / "biblioteca" / f"{f.prefisso}_2026-08.zim"))
    cfg.installa_margine_gb = 0.0
    origini = {"kiwix_mirror": srv.url + "/zim", "kiwix_main": srv.url + "/zim",
               "piper": srv.url + "/piper", "sherpa": srv.url + "/sherpa"}
    inst = Installazioni(cfg, origini=origini, log=lambda m: None)
    pcs = {"portatile": FakePC(volume=40, luminosita=80)}
    # Con i tool degli schermi e degli agenti, come in Calliope (schermi accesi di
    # predefinito e agenti con dgx.yaml, 02/10)
    reg = build_registry(pc=pcs, documenti=FORMATI, casa=False, schermi=True, agenti=True)
    registro = registro_finto()
    brains = {}
    for sessione, chi, livello, come, frase, atteso, controllo in CASI:
        key = (sessione, chi)
        if key not in brains:
            ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(chi, livello),
                              speaker=None, pc=pcs, capacita=registro, installazioni=inst)
            brains[key] = Brain(cfg, reg, ctx)
        b = brains[key]
        b.tool_ctx.speaker_ctx = SpeakerCtx(chi, livello, come)
        t0 = time.perf_counter()
        primo, parti = None, []
        for pezzo in b.stream_reply(frase, livello):
            if primo is None and pezzo.strip():
                primo = time.perf_counter() - t0
            parti.append(pezzo)
        totale = time.perf_counter() - t0
        risposta = "".join(parti).strip()
        if atteso == "installa_avvia":
            time.sleep(0.3)
        tools = [t["nome"] for t in b.last_tools]
        if atteso == "qualsiasi":
            ok_tool = True
        elif atteso is None:
            # Nessun avvio né gestione: il controllo dice il resto (niente scaricato)
            ok_tool = not ({"installa_avvia", "installa_gestisci"} & set(tools))
        elif isinstance(atteso, tuple):
            ok_tool = any(t in atteso for t in tools) or (None in atteso and not
                                                         (INSTALLA & set(tools)))
        else:
            ok_tool = atteso in tools
        try:
            ok_stato = bool(controllo(risposta, tmp, srv, inst))
        except Exception as e:  # noqa: BLE001
            ok_stato, risposta = False, f"{risposta} [controllo: {e}]"
        argomenti = "; ".join(f"{t['nome']}({', '.join(f'{k}={v!r}' for k, v in t['argomenti'].items())})"
                              for t in b.last_tools) or "—"
        verifica(f"[{giro}] {chi or 'ospite'}: «{frase}» → {argomenti}", ok_tool and ok_stato,
                 f"{primo or 0:.2f}/{totale:.2f}s  {risposta[:140]!r}")
        righe.append((giro, frase, ok_tool and ok_stato, primo or 0, totale))
    inst.close()
    srv.ferma()

prime = sorted(r[3] for r in righe)
print(f"\nprima frase mediana {prime[len(prime) // 2]:.2f}s, massimo {prime[-1]:.2f}s; "
      f"riuscite {sum(r[2] for r in righe)}/{len(righe)}")
print(f"{errori} errori" if errori else "Tutto a posto.")
sys.exit(1 if errori else 0)
