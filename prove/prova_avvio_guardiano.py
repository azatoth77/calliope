"""
Prova a secco dell'avvio di minori e guardiano (05/11/2026, issue #394). calliope/main.py
(`Avvio._minori_e_guardiano`, `_regole_e_guardiano`, `_ripasso_da_ascoltare`).

    python prove/prova_avvio_guardiano.py

Da `abc962e8` (Studio 9, 31/10) tutto ciò che seguiva il blocco dello Studio stava per sbaglio dopo
i `return` di `_ripasso_da_ascoltare`: con lo Studio spento o in ombra, col ripasso spento o senza
speaker niente guardiano, tool dei minori, avvisi completi né cancelli ripresi. Qui l'avvio vero di
quel passo, con il guardiano e i cancelli finti, in ogni combinazione, con i contrari:

- con un minore in casa guardiano scaldato, `attiva_minori` chiamata e legata ai servizi, avvisi
  col cassetto, la ricostruzione e la conservazione, cancelli ripresi, qualunque sia lo stato di
  Studio (spento, ombra, attivo, guasto), ripasso e speaker;
- contrari: senza minore il guardiano si crea ma si scalda solo con `guardiano_ospiti`, e i tool
  dei minori non entrano; col guardiano spento in configurazione nessun guardiano, il resto sì;
  con `minori_enabled: false` niente cancelli né guardiano;
- `_ripasso_da_ascoltare` da solo si occupa solo del ripasso, e il ripasso parte solo con lo Studio
  attivo, `studio_ascolta: attiva` e lo speaker.
Nomi di fantasia, un minore di casa. Niente modelli né rete: ~2 s.
"""
import atexit
import datetime
import os
import shutil
import sys
import tempfile
import threading
import types
from unittest import mock

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(QUI))
sys.path.insert(0, QUI)

from calliope import main as M, minori  # noqa: E402
from calliope import studio as studio_mod  # noqa: E402
from calliope.ciclo import Servizi  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.speaker_id import UserProfile  # noqa: E402
from calliope.tools.registry import ToolRegistry  # noqa: E402

errori = 0
CARTELLA = tempfile.mkdtemp(prefix="calliope-avvio-guardiano-")
atexit.register(shutil.rmtree, CARTELLA, ignore_errors=True)   # l'ultimo: dopo le chiusure


def verifica(nome, cond, extra=""):
    global errori
    if not cond:
        errori += 1
    print(("ok  " if cond else "ERR ") + nome + (f"  ({extra})" if extra and not cond else ""),
          flush=True)


class GuardianoFinto:
    """Senza Ollama: conta i caricamenti (il vero carica il modello in `prepara`)."""
    ultimo_errore = None

    def __init__(self, cfg):
        self.scaldato = threading.Event()

    def prepara(self):
        self.scaldato.set()
        return True

    def close(self):
        pass


class CancelliFinti:
    def __init__(self, cfg, log=None, registra=None, percorso=None):
        self.percorso = percorso


class SpeakerFinto:
    pronuncia = None

    def __init__(self):
        self.caricate = []

    def preload(self, voci):
        self.caricate.extend(voci)

    def voce_per(self, path):
        return None


def nato(anni):
    oggi = datetime.date.today()
    return f"{oggi.year - anni}-01-01"


def registro_persone(minore=True):
    """Chi amministra e, se c'è, un minore di casa."""
    users = {"carlo": UserProfile("Carlo")}
    if minore:
        users["luca"] = UserProfile("Luca", nascita=nato(12), tutori=["carlo"])
    return types.SimpleNamespace(users=users, by_id=lambda i: users.get(i))


def avvio_finto(nome, studio="spento", ripasso="attiva", speaker=True, minore=True, ospiti=False,
                guardiano=True, abilitati=True, cancelli_su_disco=True):
    """Un `Avvio` senza il lucchetto e i modelli, con la sua cartella e i servizi veri."""
    cartella = os.path.join(CARTELLA, nome)
    os.makedirs(cartella)
    cfg = Config()
    cfg.memory_db = os.path.join(cartella, "memoria.db")
    cfg.studio_modo = studio
    cfg.studio_ascolta = ripasso
    cfg.guardiano_ospiti = ospiti
    cfg.guardiano_enabled = guardiano
    cfg.minori_enabled = abilitati
    if cancelli_su_disco:
        with open(os.path.join(cartella, "cancelli.json"), "w", encoding="utf-8") as f:
            f.write("{}")
    a = M.Avvio.__new__(M.Avvio)
    a.cfg = cfg
    a.s = Servizi(cfg)
    a.s.registry = registro_persone(minore)
    a.s.tools = ToolRegistry()
    a.s.cassetto = object()
    a.s.conserva = types.SimpleNamespace(avvisi=None)
    if speaker:
        a.speaker = SpeakerFinto()
    return a


def lancia(a, studio_guasto=False):
    """Il passo dell'avvio. Il guardiano e i cancelli finti restano solo qui dentro."""
    guasto = mock.patch.object(studio_mod, "prepara", side_effect=RuntimeError("guasto"))
    with mock.patch.object(M.guardia, "Guardiano", GuardianoFinto), \
            mock.patch.object(M.cancelli_mod, "Cancelli", CancelliFinti):
        if studio_guasto:
            with guasto:
                a._minori_e_guardiano()
        else:
            a._minori_e_guardiano()
    return a.s


def tutto_acceso(nome, s):
    """Le regole dei minori e il guardiano, tutti: con un minore in casa non dipendono da altro."""
    verifica(f"{nome}: il guardiano c'è", isinstance(s.guardiano, GuardianoFinto))
    verifica(f"{nome}: il guardiano si scalda subito",
             s.guardiano is not None and s.guardiano.scaldato.wait(2))
    verifica(f"{nome}: attiva_minori legata ai servizi",
             getattr(s.attiva_minori, "__func__", None) is M.Avvio.attiva_minori)
    verifica(f"{nome}: attiva_minori chiamata, i tool dei minori ci sono",
             s.tools.get("minore_gestisci") is not None
             and s.tools.get("richiesta_tutore") is not None)
    av = minori.avvisi()
    verifica(f"{nome}: gli avvisi col cassetto, la ricostruzione e la conservazione",
             av.cassetto is s.cassetto and callable(av.trascrizione_dopo)
             and s.conserva.avvisi is av)
    verifica(f"{nome}: i cancelli ripresi dal disco",
             isinstance(s.cancelli, CancelliFinti) and s.cancelli.percorso == s.cancelli_percorso)
    # Di nuovo dopo la prima: i servizi non la ripetono (ciclo.py, dopo una registrazione)
    if s.attiva_minori is not None:
        verifica(f"{nome}: attiva_minori due volte non ripete i tool", s.attiva_minori() is False)


# ── con un minore in casa: ogni stato di Studio, ripasso e speaker ──
COMBINAZIONI = [
    ("studio spento", dict(studio="spento")),
    ("studio spento, ripasso spento, senza speaker",
     dict(studio="spento", ripasso="spenta", speaker=False)),
    ("studio in ombra", dict(studio="ombra")),
    ("studio attivo, ripasso spento", dict(studio="attivo", ripasso="spenta")),
    ("studio attivo, senza speaker", dict(studio="attivo", speaker=False)),
    ("studio attivo, ripasso spento, senza speaker",
     dict(studio="attivo", ripasso="spenta", speaker=False)),
    ("studio attivo, ripasso acceso, con speaker", dict(studio="attivo")),
]
for i, (nome, opzioni) in enumerate(COMBINAZIONI):
    s = lancia(avvio_finto(f"c{i}", **opzioni))
    tutto_acceso(nome, s)
    if s.studio is not None:
        verifica(f"{nome}: lo Studio conosce il guardiano (il copione del riassunto)",
                 s.studio.guardiano is s.guardiano)
    verifica(f"{nome}: la sintesi del ripasso solo col ripasso acceso e lo speaker",
             (getattr(s.studio, "sintesi", None) is not None)
             == (opzioni.get("studio") == "attivo" and opzioni.get("ripasso", "attiva") == "attiva"
                 and opzioni.get("speaker", True)))

s = lancia(avvio_finto("guasto", studio="attivo"), studio_guasto=True)
verifica("studio guasto: lo Studio non c'è", s.studio is None)
tutto_acceso("studio guasto", s)

# ── contrari ──
s = lancia(avvio_finto("nessuno", minore=False))
verifica("senza minore: il guardiano si crea (può servire a un ospite)",
         isinstance(s.guardiano, GuardianoFinto))
verifica("senza minore né guardiano_ospiti: non si carica",
         s.guardiano is not None and not s.guardiano.scaldato.wait(0.2))
verifica("senza minore: attiva_minori legata (un minore si può registrare dopo)",
         getattr(s.attiva_minori, "__func__", None) is M.Avvio.attiva_minori)
verifica("senza minore: i tool dei minori non ci sono", s.tools.get("minore_gestisci") is None)
s.registry.users["luca"] = UserProfile("Luca", nascita=nato(12), tutori=["carlo"])
verifica("un minore registrato dopo: attiva_minori aggiunge i tool ora",
         s.attiva_minori() is True and s.tools.get("minore_gestisci") is not None)

s = lancia(avvio_finto("nessuno_ospiti", minore=False, ospiti=True))
verifica("senza minore ma con guardiano_ospiti: si carica subito",
         s.guardiano is not None and s.guardiano.scaldato.wait(2))

s = lancia(avvio_finto("spento", guardiano=False))
verifica("guardiano spento in configurazione: non c'è", s.guardiano is None)
verifica("guardiano spento in configurazione: i tool dei minori ci sono lo stesso",
         s.tools.get("minore_gestisci") is not None)
verifica("guardiano spento in configurazione: i cancelli ripresi lo stesso",
         isinstance(s.cancelli, CancelliFinti))

s = lancia(avvio_finto("disabilitati", abilitati=False))
verifica("minori_enabled spento: niente guardiano", s.guardiano is None)
verifica("minori_enabled spento: niente cancelli",
         s.cancelli_percorso is None and s.cancelli is None)

s = lancia(avvio_finto("senza_file", cancelli_su_disco=False))
verifica("senza il file dei cancelli: nessuno da riprendere, il percorso c'è",
         s.cancelli is None and s.cancelli_percorso is not None)

# ── il ripasso si occupa solo del ripasso ──
a = avvio_finto("solo_ripasso", studio="attivo")
a.s.studio = types.SimpleNamespace(per_modello=lambda: True, sintesi=None)
with mock.patch.object(M.guardia, "Guardiano", GuardianoFinto):
    a._ripasso_da_ascoltare()
verifica("il ripasso da solo: la sintesi c'è", a.s.studio.sintesi is not None)
verifica("il ripasso da solo: non crea il guardiano", a.s.guardiano is None)
verifica("il ripasso da solo: non lega attiva_minori né registra i tool",
         a.s.attiva_minori is None and a.s.tools.get("minore_gestisci") is None)

print(f"\n{'TUTTO OK' if not errori else str(errori) + ' ERRORI'}", flush=True)
sys.exit(1 if errori else 0)
