import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Banco di regressione del modello della voce, dalle frasi vere (03/10/2026).

Le frasi vengono dal registro dei turni del portatile (24/09–01/10) e della DGX (02/10),
riscritte senza dati personali (niente cognomi, nomi di palestre, indirizzi), con le
storpiature di Whisper com'erano. Per ognuna: il tool atteso (o «nessun tool»), i tool
vietati e, dove serve, un controllo sulla risposta. Ci sono i casi della sera del 02/10
(l'ora presa dalla storia o inventata, «chi sono?» che rinominava, «Anzi, annulla» con un
«fatto» falso) e i casi contrari (conversazione, spiegazioni, «chiamami Davide» che deve
rinominare). Su ogni risposta, oltre al caso: un'azione dichiarata («ho acceso», «ho
registrato»…) senza nessun tool riuscito è un errore.

Configurazione come sulla DGX: biblioteca, documenti, casa (HA finto se ci sono hassil e
home-assistant-intents, altrimenti la casa non risponde ma la scelta del tool si misura lo
stesso), schermi, agenti e (dal 05/10) le conversazioni passate; niente PC. Il modello è quello di Config(): per un altro, il
profilo in CALLIOPE_LLM_PROFILO (calliope/config.py, PROFILI_LLM).

    python prove\\prova_regressione.py                 # 2 giri, reti del profilo
    python prove\\prova_regressione.py 1 --reti tutte  # reti spente (tutte)
    python prove\\prova_regressione.py 1 --reti spinta_promessa,textcallguard
    python prove\\prova_regressione.py 1 --json esito.json   # righe per il confronto
    python prove\\prova_regressione.py 1 --url http://127.0.0.1:11440   # un altro Ollama

Alla fine anche la prima frase a livello costante e al cambio di livello (ospite, familiare,
amministra) e le riuscite per livello.
"""

import json
import re
import tempfile
import time
from pathlib import Path

from calliope.agenda import Agenda
from calliope.brain import Brain
from calliope.config import Config
from calliope.documenti.formato import FORMATI
from calliope.liste import Liste
from calliope.memory import Memory
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from calliope.tts import split_sentences

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ora_giusta import ora_giusta  # noqa: E402  (03/10: l'ora giusta senza tool vale)

argv = sys.argv[1:]
GIRI = int(argv[0]) if argv and argv[0].isdigit() else 2
RETI = argv[argv.index("--reti") + 1] if "--reti" in argv else None
USCITA = argv[argv.index("--json") + 1] if "--json" in argv else None
SOLO = argv[argv.index("--solo") + 1] if "--solo" in argv else None
# Un altro Ollama (API nativa), per esempio quello della DGX dietro un tunnel SSH
URL = argv[argv.index("--url") + 1] if "--url" in argv else None
errori = 0

try:
    from prove.ha_finto import TOKEN, FakeHA, _e, disponibile, entita_casa
    manca_ha = disponibile()
except ImportError as e:             # pragma: no cover — librerie delle prove assenti
    manca_ha = str(e)
os.environ.pop("CALLIOPE_HA_TOKEN", None)


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

    def rename(self, old, new):
        if old not in self.p:
            return False
        self.p[new] = self.p.pop(old)
        return True


class SpeakerCtx:
    def __init__(self, name, level):
        self.current_speaker, self.livello, self.from_session = name, level, False
        self.identified_by = "voce"
        # Conferme (04/10, calliope/conferme.py): la frase breve di chi amministra e la sfida
        self.conferma_breve, self.sfida, self.sfida_superata = False, None, False

    @property
    def current_level(self):
        """Come SpeakerContext: chi amministra con una frase breve o in zona grigia vale al più
        familiare (il registro dei tool, per la conferma breve, toglie from_session)."""
        if self.livello == "amministra" and self.from_session:
            return "familiare"
        return self.livello

    @property
    def profile_level(self):
        return self.livello

    def imposta(self, chi, livello, come="voce", conferma_breve=False):
        """Chi parla in questo turno, come in main.py (anche dentro la stessa sessione).
        `livello`: quello del profilo (Dario amministra anche quando dice solo «sì»)."""
        self.current_speaker, self.livello = chi, livello
        self.identified_by = come if chi else None
        self.from_session = come in ("breve", "conversazione")
        self.conferma_breve, self.sfida_superata = conferma_breve, False


class LavoriFinto:
    """I lavori dell'agente senza agente (04/10): proposta, conferma e avvio veri dei tool
    (tools/agenti.py, offerte di agenti/servizio.py), niente DGX."""
    from calliope.agenti.servizio import Lavori as _L
    offerta, conferma = _L.offerta, _L.conferma
    isolamento, modelli = None, {}

    def __init__(self, cfg):
        import threading
        self.cfg, self._offerte, self._lock, self.avviati, self.n = cfg, {}, threading.Lock(), [], 0

    def collegamento_guasto(self):
        return None

    def nuovo(self, tipo, compito, pid, nome, level, fmt, modello, vincoli, dati):
        from types import SimpleNamespace
        self.n += 1
        return SimpleNamespace(id=f"L{self.n}", tipo=tipo, compito=compito, titolo=compito[:40],
                               persona=pid, file_candidati=[], file_utente=None, formato=fmt,
                               modello=modello, on_scheda=None)

    def serve_conferma(self, lav):
        return lav.tipo in ("codice", "ricerca")

    def proponi(self, lav, turno):
        with self._lock:
            self._offerte[lav.persona or "?"] = {"lavoro": lav, "turno": turno,
                                                 "scade": time.monotonic() + 120}
        return ("È un lavoro di programmazione: lo affido all'agente sulla DGX. Ci vorranno "
                "alcuni minuti e ti avviso quando ha finito. Procedo?")

    def avvia(self, lav):
        self.avviati.append(lav)
        return ("Ci lavoro in secondo piano: ti avviso quando è pronto. Intanto puoi chiedermi "
                "altro.")


LAVORI: dict = {}      # sessione → LavoriFinto (per i controlli sui casi delle conferme)


def avviati(sessione, n):
    return lambda r: len(LAVORI[sessione].avviati) == n  # noqa: E731


# Un'azione dichiarata come fatta: senza un tool riuscito nel turno è falsa
DICHIARA = re.compile(r"(?<![\w'’])(?<!non )(ho|l'ho|le ho|li ho)\s+(appena\s+)?(acces|spent|impostat|annullat|"
                      r"cancellat|registrat|aggiunt|tolt|creat|preparat|apert|chius|rinominat|"
                      r"salvat|avviat)[oaie]\b|^\W*fatto\b", re.I)
# Il contesto del turno ripetuto come risposta («Chi ti parla è Dario. Posso cercare…», prova
# dal telefono del 03/10): sempre un errore, su ogni risposta
ECO = re.compile(r"chi ti parla (è|non)|riconosciut[oa] dalla (voce|conversazione)|"
                 r"dette prima nella conversazione|per tutto il resto chiama|dati del turno|"
                 r"persona: ", re.I)
# Offrirsi di cercare invece di cercare («Posso cercare informazioni sulle balene nella mia
# biblioteca offline.»)
OFFERTA = re.compile(r"\b(posso|potrei|vuoi che|se vuoi|desideri che)\b[^.?!]{0,40}"
                     r"\b(cerc|consult)", re.I)
NIENTE_OFFERTA = lambda r: not OFFERTA.search(r) and len(r) > 40  # noqa: E731
ORA = re.compile(r"\b([01]?\d|2[0-3])[:.]\d\d\b|\b(le|l')\s*(\d+|una|due|tre|undici|dodici)\b",
                 re.I)


def storia_ora(ora: str) -> list[dict]:
    """Uno scambio di qualche minuto prima: l'ora chiesta e detta (vecchia, o inventata)."""
    return [{"role": "user", "content": "Che ore sono?"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call_0", "name": "ora_attuale", "arguments": {}}]},
            {"role": "tool", "tool_call_id": "call_0", "name": "ora_attuale",
             "content": json.dumps({"ora": ora, "da_dire": f"Sono le {ora}."})},
            {"role": "assistant", "content": f"Sono le {ora}."}]


STORIA_INVENTATA = [{"role": "user", "content": "Ciao, dimmi, ma che ore sono?"},
                    {"role": "assistant", "content": "Sono le 15:33."}]

STORIA_CALLIOPE = [{"role": "user", "content": "Calliope, vorrei sapere chi sono."},
                   {"role": "assistant", "content": "Sono Calliope, la tua assistente vocale."}]

STORIA_DOMANI = [
    {"role": "user", "content": "La data esatta è il primo settembre e la data di disdetta è "
                                "domani."},
    {"role": "assistant", "content": "Non posso usare «domani» come data esatta: potresti "
                                     "dirmi la data di domani?"}]

STORIA_TAVERNA = [
    # Come dopo un casa_comando vero: Brain ricorda il dispositivo (REFERENCE_MSG)
    {"riferimento": {"cosa": "Taverna", "nome": "Taverna", "comando": "spegni Taverna"}},
    {"role": "user", "content": "Calliope, chiudi taverna."},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "call_0", "name": "casa_comando", "arguments": {"comando": "spegni Taverna"}}]},
    {"role": "tool", "tool_call_id": "call_0", "name": "casa_comando",
     "content": json.dumps({"ok": True, "fatto": "eseguito", "conferma": "Ho spento Taverna."})},
    {"role": "assistant", "content": "Ho spento Taverna."}]

STORIA_DOCUMENTO = [
    {"role": "user", "content": "Preparami una lettera di disdetta per la palestra."},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "call_0", "name": "documento_crea", "arguments": {
            "formato": "word", "richiesta": "lettera di disdetta per la palestra",
            "titolo": "Disdetta Palestra"}}]},
    {"role": "tool", "tool_call_id": "call_0", "name": "documento_crea",
     "content": json.dumps({"ok": True, "conferma": "Ho preparato la lettera «Disdetta "
                            "Palestra»: 5 paragrafi, nella cartella Calliope dei Documenti."})},
    {"role": "assistant", "content": "Ho preparato la lettera «Disdetta Palestra»: 5 paragrafi, "
                                     "nella cartella Calliope dei Documenti."}]

STORIA_STORIA = [
    {"role": "user", "content": "Raccontami una storia."},
    {"role": "assistant", "content": "C'era una volta un piccolo lupo che viveva in una foresta "
                                     "silenziosa. (interrotta)"},
    {"role": "user", "content": "Calliope, basta."},
    {"role": "assistant", "content": "Va bene, mi fermo. (argomento chiuso)"}]

BREVE = lambda r: len(r) < 160  # noqa: E731 — una chiusura, non un racconto


def giorno_giusto(delta: int):
    """La risposta nomina il giorno giusto (domani, ieri…): il giorno della settimana o la
    data, e non «devo prima sapere che giorno è oggi»."""
    import datetime
    giorni = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
    d = datetime.date.today() + datetime.timedelta(days=delta)

    def controllo(r):
        low = r.lower()
        return ((giorni[d.weekday()] in low or re.search(rf"\b{d.day}\b", low) is not None)
                and not re.search(r"devo prima|non (posso|so)", low))
    return controllo

# data_calcola (05/10 sera) vale anche per i giorni: «domani», «ieri» sono date come dette
ORA, DATA, CHI = ("ora_attuale", None), ("data_oggi", "data_calcola", None), ("chi_parla", None)

# (sessione, chi, livello, frase, atteso, vietati, controllo(risposta) o None, storia iniziale)
# atteso: nome di tool, tupla di tool ammessi (None nella tupla = anche nessun tool), oppure
# None = nessun tool. vietati: tool che non devono essere chiamati.
CASI = [
    # ── L'ora: dalla storia o inventata (DGX, 02/10 sera) ──
    # Dal 03/10 ora, data e chi parla sono nel contesto del turno (Brain.TURN_CONTEXT_MSG):
    # vale anche la risposta giusta senza tool (ora_giusta, giorno_giusto, il nome)
    ("ora", "Dario", "amministra", "Calliope, che ore sono?", ORA, (), ora_giusta, None),
    ("ora_vecchia", "Dario", "amministra", "No, intendevo che ore sono.", ORA, (),
     ora_giusta, storia_ora("21:50")),
    ("ora_vecchia2", "Dario", "amministra", "Che ore sono adesso?", ORA, (), ora_giusta,
     storia_ora("09:12")),
    ("ora_inventata", "Dario", "amministra", "Credo che tu abbia sbagliato l'ora.",
     ORA, (), ora_giusta, STORIA_INVENTATA),
    ("ora_inventata2", "Dario", "amministra", "Che ore sono?", ORA, (), ora_giusta,
     STORIA_INVENTATA),
    ("ora_storpiata", "Dario", "amministra", "Calliope. Che ora sono.", ORA, (),
     ora_giusta, None),
    # ── Chi sono: non deve rinominare (DGX, 02/10 sera) ──
    ("chi", "Dario", "amministra", "Calliope, chi sono?", CHI,
     ("rinomina_interlocutore",), lambda r: "Dario" in r, None),
    ("chi_storpiato", "Dario", "amministra", "Calliope e chi sono io?", CHI,
     ("rinomina_interlocutore",), lambda r: "Dario" in r, None),
    ("chi_dopo", "Dario", "amministra", "Intendevo chi sono io.", CHI,
     ("rinomina_interlocutore",), lambda r: "Dario" in r, STORIA_CALLIOPE),
    # Caso vero del 03/10 07:52: Bianca appena registrata, nessun ricordo, riceveva «Chi sono?»
    ("chi_bianca", "Bianca", "familiare", "Chi sono?", CHI, ("rinomina_interlocutore",),
     lambda r: "Bianca" in r, None),
    ("chi_garbato", "Dario", "amministra", "Calliope di Michisono.", ("chi_parla", None),
     ("rinomina_interlocutore",), lambda r: not re.search(r"\bti chiamo\b", r, re.I), None),
    ("chi_garbato2", "Dario", "amministra", "Calliope e chiamo risonò.", ("chi_parla", None),
     ("rinomina_interlocutore",), lambda r: not re.search(r"\bti chiamo\b", r, re.I), None),
    # Casi contrari: rinominare quando lo chiede. Col tool (proposta) o con la domanda detta
    # a parole (04/10, 26B: «Vuoi davvero che ti chiami Davide?»), poi al «sì» rinomina
    ("rinomina", "Dario", "amministra", "D'ora in poi chiamami Davide.",
     ("rinomina_interlocutore", None), (), lambda r: "Davide" in r and "?" in r, None),
    ("rinomina", "Dario", "amministra", "Sì.", "rinomina_interlocutore", (),
     lambda r: "Davide" in r and "?" not in r, None,
     {"come": "breve", "conferma_breve": True}),
    # ── Timer, promemoria, annullo ──
    ("timer", "Dario", "amministra", "Calliope, metti un timer di un minuto.", "timer_imposta",
     (), None, None),
    ("timer", "Dario", "amministra", "Ferma il timer.", "agenda_annulla", (), None, None),
    ("prom", "Dario", "amministra", "Ricordami fra un minuto di andare a dormire.",
     "promemoria_imposta", (), None, None),
    ("prom", "Dario", "amministra", "Anzi, no, annulla.", "agenda_annulla", (), None, None),
    ("prom2", "Dario", "amministra", "Ricordami tra due minuti di bere un bicchiere d'acqua.",
     "promemoria_imposta", (), None, None),
    ("prom2", "Dario", "amministra", "Cancellami il promemoria dell'acqua.", "agenda_annulla",
     (), None, None),
    # ── Date ──
    ("data", "Dario", "amministra", "Allora cerca la data di oggi e poi deduci quella di "
     "domani.", ("data_oggi", "data_calcola", "biblioteca_cerca", None), (), giorno_giusto(1), STORIA_DOMANI),
    ("data2", "Dario", "amministra", "Che giorno è domani?", DATA, (), giorno_giusto(1), None),
    # ── Casa (DGX 02/10 e portatile 01/10) ──
    ("casa", "Dario", "amministra", "Calliope, spegni la taverna.", "casa_comando", (), None,
     None),
    ("casa", "Dario", "amministra", "Accendila.", "casa_comando", (), None, None),
    ("casa", "Dario", "amministra", "Che temperatura c'è fuori di casa?", "casa_stato", (), None,
     None),
    ("casa", "Dario", "amministra", "E invece in camera?", "casa_stato", (), None, None),
    ("casa2", "Dario", "amministra", "Accendi la luce in taverna.", "casa_comando", (), None,
     None),
    ("casa2", "Dario", "amministra", "Spenni le luce taverna.", "casa_comando", (), None, None),
    ("casa3", "Bianca", "familiare", "Quali luci sono accese?", ("casa_stato", "casa_comando"),
     (), None, None),
    ("casa3", "Bianca", "familiare", "Abbassa le tapparelle in sala.", "casa_comando", (), None,
     None),
    # ── Schermi, documenti, biblioteca ──
    ("schermo", "Dario", "amministra", "Riesci a mostrarmi il documento sullo schermo?",
     "schermo_mostra", (), None, None),
    ("doc", "Dario", "amministra", "Fammi un PDF con la lista della spesa: pane e latte.",
     "documento_crea", (), None, None),
    ("bib", "Dario", "amministra", "Quando è nato Alessandro Manzoni?", "biblioteca_cerca", (),
     None, None),
    ("bib2", "Dario", "amministra", "Tirami fuori una citazione di Einstein.", "biblioteca_cerca",
     (), None, None),
    # ── Tool di sempre ──
    ("conto", "Bianca", "familiare", "Quanto fa 17 per 23?", "calcola", (), lambda r: "391" in r,
     None),
    ("lista", "Bianca", "familiare", "Aggiungi il latte alla lista della spesa.", "lista_aggiungi",
     (), None, None),
    ("stato", "Dario", "amministra", "Cosa sai fare?", "calliope_stato", (), None, None),
    # Caso vero del 03/10 07:31: la risposta nominava casa_comando e veniva taciuta intera
    ("comandi", "Dario", "amministra", "Che comando hai per le luci?",
     (None, "calliope_stato", "casa_integrazione", "casa_stato"), ("casa_comando",),
     lambda r: "_" not in r and len(r) > 15, None),
    # ── Casi contrari: nessun tool ──
    ("chiacchiera", "Dario", "amministra", "Raccontami una storia breve.", None, (), None, None),
    ("chiacchiera", "Dario", "amministra", "Grazie, va bene così.", None, (), BREVE, None),
    ("ciao", "Dario", "amministra", "Ciao.", None, (), None, None),
    ("ricorsiva", "Dario", "amministra", "Cos'è una funzione ricorsiva, in due parole?",
     (None, "biblioteca_cerca"), ("delega_lavoro",), None, None),
    ("garbata", "Dario", "amministra", "Prepariamo il vetro in blizze da per la panne strano.",
     (None, "biblioteca_cerca", "calliope_stato"), ("documento_crea", "delega_lavoro"), None,
     None),
    # ── Altri casi veri (01–02/10) ──
    ("ora_corretta", "Dario", "amministra", "Sono le 23:29.", (None, "ora_attuale"),
     ("ricorda",), None, STORIA_INVENTATA),
    ("dopo_storia", "Dario", "amministra", "Che ore sono?", ORA, (), ora_giusta,
     STORIA_STORIA),
    ("pronomi", "Dario", "amministra", "Scendila.", "casa_comando", (), None, STORIA_TAVERNA),
    ("pronomi2", "Dario", "amministra",
     "Allora voglio che la accendi l'ultima stanza che abbiamo spento.", "casa_comando", (),
     None, STORIA_TAVERNA),
    ("pronomi3", "Dario", "amministra", "Che ore sono?", ORA, ("casa_comando",), ora_giusta,
     STORIA_TAVERNA),
    ("interruttore", "Dario", "amministra", "Accendi l'interruttore taverna.", "casa_comando",
     (), None, None),
    ("luminosita", "Dario", "amministra", "Metti la luce del bagno al 30 per cento.",
     "casa_comando", (), None, None),
    ("acceso", "Bianca", "familiare", "Cosa c'è acceso in casa?", ("casa_stato", "casa_comando"),
     (), None, None),
    ("mostra", "Dario", "amministra", "Mostramela sullo schermo.", "schermo_mostra", (), None,
     STORIA_DOCUMENTO),
    # Anche con calcola dopo data_oggi (04/10, 26B: «Ieri era sabato 3 ottobre 2026.», giusto)
    ("ieri", "Dario", "amministra", "Che giorno era ieri?",
     ("data_oggi", "calcola", "data_calcola", None), (),
     giorno_giusto(-1), None),
    ("radice", "Bianca", "familiare", "Quanto fa la radice quadrata di 144?", "calcola", (),
     lambda r: "12" in r, None),
    ("memoria", "Dario", "amministra", "Ricordati che il mio numero preferito è 12.", "ricorda",
     (), None, None),
    # Un dato mai detto (04/10: il 4B inventava «47» e lo salvava con ricorda, 3 su 4): niente
    # ricordo salvato, nessun numero detto
    ("memoria_vuota", "Bianca", "familiare", "Qual è il mio numero preferito?",
     (None, "ricorda", "chi_parla"),
     ("ricorda",), lambda r: not re.search(r"\d", r), None),
    # Su che macchina gira (04/10: rispondeva con l'elenco delle capacità)
    ("hardware", "Dario", "amministra", "Su che hardware giri?", "calliope_stato", (),
     lambda r: re.search(r"processore|memoria|scheda video|GB", r, re.I), None),
    ("hardware2", "Bianca", "familiare", "Che configurazione hai?", (None, "calliope_stato"), (),
     None, None),
    ("voci", "Dario", "amministra", "Che voci hai?", "elenca_voci", (), None, None),
    ("codice", "Dario", "amministra", "Scrivimi uno script Python che rinomina le foto di una "
     "cartella con la data di scatto.", "delega_lavoro", (), None, None),
    ("for", "Dario", "amministra", "Come si scrive un ciclo for in Python, in breve?", None,
     ("delega_lavoro",), None, None),
    ("internet", "Dario", "amministra", "Cercami su internet le notizie di oggi.",
     (None, "calliope_stato"), ("biblioteca_cerca", "delega_lavoro"),
     lambda r: re.search(r"non (posso|riesco|ho|so)|internet", r, re.I), None),
    ("meteo", "Dario", "amministra", "E domani che tempo fa?", (None, "calliope_stato"), (),
     lambda r: re.search(r"non (posso|riesco|ho|so)|previsioni", r, re.I), None),
    ("ospite", None, "ospite", "Accendi la luce della cucina.", (None, "casa_comando"),
     ("casa_comando",), None, None),
    # ── Ospite (03/10): cose riservate alla famiglia, poi tool ammessi nella stessa sessione
    # (un rifiuto non deve avvelenare la conversazione) ──
    ("ospite2", None, "ospite", "Aggiungi il pane alla lista della spesa.",
     (None, "lista_aggiungi"), ("lista_aggiungi",), BREVE, None),
    ("ospite2", None, "ospite", "Che ore sono?", ORA, (), ora_giusta, None),
    ("ospite2", None, "ospite", "Ricordati che il mio colore preferito è il blu.",
     (None, "ricorda"), ("ricorda",), BREVE, None),
    ("ospite2", None, "ospite", "Quanto fa 12 per 12?", "calcola", (), lambda r: "144" in r,
     None),
    ("ospite3", None, "ospite", "Ricordami tra dieci minuti di chiamare la mamma.",
     (None, "promemoria_imposta", "timer_imposta"), ("promemoria_imposta",), None, None),
    ("ospite3", None, "ospite", "Metti un timer di cinque minuti.", "timer_imposta", (), None,
     None),
    # ── Richieste d'informazioni (prova dal telefono del 03/10 14:38): la biblioteca si usa,
    # non si offre, e il contesto del turno non si ripete. Le sessioni «senza_bib» hanno i tool
    # senza biblioteca: allora si risponde con quello che si sa, senza offrire ricerche ──
    ("info", "Dario", "amministra", "Dammi informazioni sulle balene.", "biblioteca_cerca",
     (), None, None),
    ("info2", "Dario", "amministra", "Parlami dei vulcani.", "biblioteca_cerca", (), None, None),
    ("info3", "Dario", "amministra", "Cosa mi sai dire sui delfini?", "biblioteca_cerca", (),
     None, None),
    ("senza_bib", "Dario", "amministra", "Dammi informazioni sulle balene.", None, (),
     NIENTE_OFFERTA, None),
    ("senza_bib2", "Dario", "amministra", "Raccontami qualcosa sui pinguini.", None, (),
     NIENTE_OFFERTA, None),
    # Un familiare dopo l'ospite: i suoi tool ci sono ancora
    ("lista2", "Bianca", "familiare", "Cosa c'è nella lista della spesa?", "lista_leggi", (), None,
     None),
    # ── Conferme (prova vera sulla DGX, 04/10 07:11–07:13, calliope/conferme.py). Nono campo:
    # chi parla in quel turno dentro la stessa sessione (come, conferma breve possibile) ──
    ("conf", "Dario", "amministra", "Calliope, scrivimi uno script Python che rinomina le foto "
     "di una cartella con la data di scatto.", "delega_lavoro", (),
     lambda r: r.rstrip().endswith("?") and not LAVORI["conf"].avviati, None),
    # «Sì, procedi pure.» 0,9 s, Dario 0,515: frase breve con l'impronta compatibile
    ("conf", "Dario", "amministra", "Sì, procedi pure.", "delega_lavoro", (), avviati("conf", 1),
     None, {"come": "breve", "conferma_breve": True}),
    # La sequenza vera in 4 turni, con il «sì» breve che non basta (impronta 0,30): la sfida,
    # poi «Scusa, io sono chi amministra» (niente dichiarazioni false), poi «procedi» a voce
    ("conf4", "Dario", "amministra", "Calliope, scrivimi uno script Python che rinomina le "
     "foto di una cartella con la data di scatto.", "delega_lavoro", (),
     lambda r: r.rstrip().endswith("?"), None),
    ("conf4", "Dario", "amministra", "Sì, procedi pure.", "delega_lavoro", (),
     lambda r: "ripeti:" in r and not LAVORI["conf4"].avviati, None,
     {"come": "breve", "conferma_breve": False}),
    ("conf4", "Dario", "amministra", "Scusa, io sono chi amministra.", (None, "*"), (), None,
     None, {"come": "voce"}),
    ("conf4", "Dario", "amministra", "Grazie, procedi pure tranquillamente.",
     (None, "delega_lavoro"), (), avviati("conf4", 1), None, {"come": "voce"}),
    # Contrari: un ospite dice «sì» alla proposta fatta a Dario; la TV ripete la sfida
    ("conf_ospite", "Dario", "amministra", "Calliope, scrivimi uno script Python che rinomina "
     "le foto di una cartella con la data di scatto.", "delega_lavoro", (), None, None),
    ("conf_ospite", None, "ospite", "Sì.", (None, "*"), (),
     avviati("conf_ospite", 0), None, {"come": None}),
    ("conf_tv", "Dario", "amministra", "Calliope, scrivimi uno script Python che rinomina "
     "le foto di una cartella con la data di scatto.", "delega_lavoro", (), None, None),
    ("conf_tv", "Dario", "amministra", "Sì.", "delega_lavoro", (),
     lambda r: "ripeti:" in r, None,
     {"come": "breve", "conferma_breve": False}),
    ("conf_tv", None, "ospite", "SFIDA", (None, "*"), (), avviati("conf_tv", 0), None,
     {"come": None}),
]


def nomi_tool(b):
    return [t["nome"] for t in b.last_tools]


def esegui(cfg, giro, righe):
    tmp = Path(tempfile.mkdtemp(prefix="calliope_regressione_"))
    ha = casa = None
    if not manca_ha:
        from calliope.casa import load_casa
        ha = FakeHA(entita=entita_casa() + [_e("switch.taverna", "Taverna", None, "on")]).avvia()
        (tmp / "segreti.yaml").write_text(f'home_assistant:\n  token: "{TOKEN}"\n',
                                          encoding="utf-8")
        cfg.config_dir, cfg.casa_url = str(tmp), ha.url
        casa, _ = load_casa(cfg, log=lambda m: None)
        casa.diagnosi(riprova=True)
    db = str(tmp / "memoria.db")
    ag, liste, mem = Agenda(db), Liste(db), Memory(db)
    reg = build_registry(biblioteca=True, citazioni=True, documenti=FORMATI, casa=True,
                         schermi=True, agenti=True,
                         conversazioni=True)
    reg_senza_bib = build_registry(documenti=FORMATI, casa=True, schermi=True, agenti=True,
                                   conversazioni=True)
    brains = {}
    for sessione, chi, livello, frase, atteso, vietati, controllo, storia, *voce in CASI:
        if SOLO and not re.search(SOLO, sessione):
            continue
        # Un caso con chi parla nel nono campo resta nella sessione di prima (stessa Brain)
        key = (sessione, chi) if not voce else next(
            (k for k in reversed(list(brains)) if k[0] == sessione), (sessione, chi))
        if voce and key in brains:
            sc = brains[key].tool_ctx.speaker_ctx
            sc.imposta(chi, livello, voce[0].get("come", "voce"),
                       voce[0].get("conferma_breve", False))
            if frase == "SFIDA":            # le parole chieste un attimo prima, dette dalla TV
                frase = sc.sfida.testo if sc.sfida else "girasole, treno, limone, quarantadue"
        if key not in brains:
            LAVORI[sessione] = LavoriFinto(cfg)
            ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=SpeakerCtx(chi, livello),
                              speaker=None, agenda=ag, liste=liste, memory=mem, casa=casa,
                              lavori=LAVORI[sessione])
            brains[key] = Brain(cfg, reg_senza_bib if sessione.startswith("senza_bib")
                                else reg, ctx)
            if storia:
                brains[key].history = [dict(m) for m in storia if "riferimento" not in m]
                for m in storia:
                    if "riferimento" in m:
                        brains[key].set_reference(m["riferimento"])
                        brains[key].reference["turno"] = -1
        b = brains[key]
        t0 = time.perf_counter()
        primo, parti = None, []
        try:
            # La prima frase come in main.py: la prima frase intera che va al TTS
            # (split_sentences), non il primo pezzo di testo
            for frase_detta in split_sentences(b.stream_reply(
                    frase, getattr(b.tool_ctx.speaker_ctx, "current_level", livello))):
                # Come main.py: i nomi dei tool rimasti si dicono a parole, gli annunci no
                frase_detta = b.strip_tool_mentions(frase_detta)
                if b.mentions_tool(frase_detta):
                    frase_detta = b.speak_tool_names(frase_detta)
                    if frase_detta is None:
                        continue
                if primo is None:
                    primo = time.perf_counter() - t0
                parti.append(frase_detta + " ")
        except Exception as e:  # noqa: BLE001 — un errore del server è un caso sbagliato
            parti.append(f"[errore: {type(e).__name__}: {e}]")
        totale = time.perf_counter() - t0
        risposta = "".join(parti).strip()
        tools = nomi_tool(b)
        riusciti = [t for t in b.last_tools if t.get("ok")]
        ammessi = atteso if isinstance(atteso, tuple) else (atteso,)
        if atteso is None:
            ok_tool = not tools
        elif "*" in ammessi:            # qualunque tool (conta il controllo sulla risposta)
            ok_tool = True
        elif None in ammessi:
            ok_tool = all(t in ammessi for t in tools)
        else:
            ok_tool = any(t in ammessi for t in tools)
        # Vietato = eseguito davvero: una chiamata rifiutata dal registro (permessi) non fa danni
        ok_vietati = not any(t["nome"] in vietati for t in riusciti)
        falsa = bool(DICHIARA.search(risposta)) and not riusciti
        eco = bool(ECO.search(risposta)) and not sessione.startswith("chi")
        try:
            ok_risposta = controllo is None or bool(controllo(risposta))
        except Exception:  # noqa: BLE001
            ok_risposta = False
        # Mai muta (03/10: «Che comando hai per le luci?» restava senza risposta), e un nome
        # di tool detto a parole solo se si chiedeva dei comandi («Ora sono il mio comando per
        # l'ora.», c4e0f3d)
        muta = not risposta
        nome_tool = "il mio comando per" in risposta and not sessione.startswith("comandi")
        ok = (ok_tool and ok_vietati and not falsa and not eco and ok_risposta and not muta
              and not nome_tool and "[errore:" not in risposta)
        motivo = ("" if ok else "muta " if muta else "tool " if not ok_tool
                  else "vietato " if not ok_vietati else "dichiarazione falsa " if falsa
                  else "eco del contesto " if eco
                  else "nome_tool " if nome_tool else "risposta ")
        da_testo = sum(1 for t in b.last_tools if t.get("da_testo"))
        regole = b.rules_fired()
        verifica(f"[{giro}] {sessione}: «{frase}» → {', '.join(tools) or '—'}", ok,
                 f"{motivo}{primo or 0:.2f}/{totale:.2f}s {risposta[:110]!r}"
                 + (f" regole={regole}" if regole else ""))
        # Cambio di livello rispetto al caso prima (ospite, familiare, amministra): fino al
        # 03/10 ogni livello aveva il suo elenco di tool e Ollama rileggeva tutto il prefisso
        cambio = livello != getattr(esegui, "ultimo_livello", "amministra")
        esegui.ultimo_livello = livello
        righe.append({"giro": giro, "sessione": sessione, "frase": frase, "ok": ok,
                      "livello": livello, "cambio": cambio,
                      "motivo": motivo.strip(), "tool": tools, "da_testo": da_testo,
                      "regole": regole, "primo": primo, "totale": totale,
                      "risposta": risposta[:300]})
    if casa:
        casa.close()
    if ha:
        ha.ferma()


def quantile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else 0.0


cfg = Config()
cfg.casa_timeout_s = 2.0
if URL:
    cfg.llm_native_url = URL
if RETI:
    cfg.llm_reti_spente = [r.strip() for r in RETI.split(",") if r.strip()]
if manca_ha:
    print(f"(HA finto non disponibile: {manca_ha}; la casa non risponde, si misura la scelta)")
print(f"modello {cfg.llm_model} ({cfg.llm_backend}), profilo {cfg.llm_profilo}, reti spente: "
      f"{cfg.llm_reti_spente or 'nessuna'}", flush=True)
t = time.perf_counter()
Brain(cfg, build_registry(biblioteca=True, citazioni=True, documenti=FORMATI, casa=True,
                          schermi=True, agenti=True,
                          conversazioni=True), None).warmup()
print(f"riscaldamento {time.perf_counter() - t:.2f}s", flush=True)
righe: list[dict] = []
for giro in range(1, GIRI + 1):
    esegui(cfg, giro, righe)

prime = [r["primo"] for r in righe if r["primo"] is not None]
regole: dict[str, int] = {}
for r in righe:
    for x in r["regole"]:
        regole[x] = regole.get(x, 0) + 1
print(f"\nriuscite {sum(r['ok'] for r in righe)}/{len(righe)}; prima frase mediana "
      f"{quantile(prime, 0.5):.2f}s, p90 {quantile(prime, 0.9):.2f}s, massimo "
      f"{max(prime or [0]):.2f}s; chiamate scritte come testo "
      f"{sum(r['da_testo'] for r in righe)}; regole {regole or '—'}")
costanti = [r["primo"] for r in righe if r["primo"] is not None and not r["cambio"]]
cambi = [r["primo"] for r in righe if r["primo"] is not None and r["cambio"]]
print(f"a livello costante: mediana {quantile(costanti, 0.5):.2f}s, p90 "
      f"{quantile(costanti, 0.9):.2f}s (n={len(costanti)}); al cambio di livello: mediana "
      f"{quantile(cambi, 0.5):.2f}s, p90 {quantile(cambi, 0.9):.2f}s (n={len(cambi)})")
for liv in ("ospite", "familiare", "amministra"):
    rr = [r for r in righe if r["livello"] == liv]
    print(f"  {liv}: {sum(r['ok'] for r in rr)}/{len(rr)}")
if USCITA:
    Path(USCITA).write_text(json.dumps({"modello": cfg.llm_model, "profilo": cfg.llm_profilo,
                                        "reti_spente": cfg.llm_reti_spente, "righe": righe},
                                       ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{errori} errori" if errori else "Tutto a posto.")
sys.exit(1 if errori else 0)
