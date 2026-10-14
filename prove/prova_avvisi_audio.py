"""
Trascrizione e audio negli avvisi di pericolo al tutore (14/10/2026 sera, decisione di Dario che
cambia la 0029 punto 4; calliope/avvisi_audio.py, calliope/minori.py `Avvisi`).

    python prove/prova_avvisi_audio.py

Un avviso di pericolo porta, **solo sulla scheda personale del tutore**, la trascrizione delle
righe del segnale con un po' di contesto e, con `avvisi_audio`, l'audio di quelle frasi dal suo
cassetto. A voce e nel testo dell'avviso mai le parole. A secco, con i contrari:

- l'anello in memoria: tetto in minuti e in MB (anello pieno → i più vecchi escono), «dimentica»
  di un luogo, WAV μ-law che si rilegge; spento di serie;
- turni: l'audio di un minore entra nell'anello, quello di un adulto o dello scritto no; un
  avviso acuto → trascrizione nella riga e nella scheda «avviso» del tutore, audio nel suo
  cassetto (fonte «avviso», 30 giorni, fuori dalla revisione), «Scarica l'audio» solo dal suo
  schermo (un altro schermo personale, anche di chi amministra, no); un adulto non tutore
  niente; la frase a voce senza parole; spento → niente audio, trascrizione sì;
  `avvisi_trascrizione: false` → nemmeno quella;
- stanza: il segmento di un minore e quello di un adulto con un minore presente entrano, quello
  di un adulto senza minori e una voce non riconosciuta (ospite) no; il guardiano in attiva salva
  solo i segmenti del segnale col contesto breve, in ombra niente su disco e «audio_s» nelle
  misure;
- scadenza (trascrizione oltre `avvisi_audio_giorni`, audio nel cassetto), `calliope conserva
  --svuota` (tutto e per persona), «dimentica» della stanza e delle conversazioni del tutore;
- un avviso di prima, senza trascrizione: ricostruita dalla stanza, oppure la nota «non c'è più».
Nomi di fantasia. Niente modelli né rete: ~3 s.
"""
import datetime
import json
import os
import queue
import sys
import tempfile
import threading
import time
import types

import numpy as np

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(QUI))
sys.path.insert(0, QUI)

import prova_stanza_guardia as PSG  # noqa: E402
from calliope import avvisi_audio as AA, corsie, guardiano as G, minori  # noqa: E402
from calliope.cassetto import Cassetto  # noqa: E402
from calliope.ciclo import Ciclo, Servizi, Turno, _FINE  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.conserva import Conservazione, leggi_wav  # noqa: E402
from calliope.cortesia import Cortesia  # noqa: E402
from calliope.schermi.scarica import Rifiuto, Scaricamenti  # noqa: E402
from calliope.stanza import guardia as gm  # noqa: E402

errori = 0
CARTELLA = tempfile.mkdtemp(prefix="calliope-avvisi-audio-")


def verifica(nome, cond, extra=""):
    global errori
    if not cond:
        errori += 1
    print(("ok  " if cond else "ERR ") + nome + (f"  ({extra})" if extra and not cond else ""),
          flush=True)


def tono(secondi, f=440.0):
    t = np.arange(int(16000 * secondi)) / 16000.0
    return (0.3 * np.sin(2 * np.pi * f * t)).astype(np.float32)


# ─────────────────────────── finti ───────────────────────────
class Voce:
    muto, _current_voice_path, on_parla, interrupted = False, "", None, False

    def __init__(self):
        self.detto = []

    def say(self, t):
        self.detto.append(t)

    def saying_name(self):
        return False

    def wait(self, *a):
        pass

    def interrupt(self):
        pass

    def start_turn(self):
        pass

    def chime(self, *a):
        pass


class Guardia:
    timeout_s = 1.0

    def __init__(self, cfg):
        self.cfg = cfg

    def condivide_voce(self):
        return False

    def in_parallelo(self, domanda, frase, categorie):
        import concurrent.futures
        f = concurrent.futures.Future()
        if frase is None and "farmi del male" in domanda.lower():
            f.set_result(G.Giudizio(G.PERICOLO, ("autolesionismo",)))
        else:
            f.set_result(G.Giudizio(G.OK))
        return f

    def giudica_domanda(self, t):
        return G.Giudizio(G.OK)

    def gravita(self, frase):
        return G.Giudizio(G.ACUTO, ms=5.0)

    def verifica(self, primo, risposta):
        return G.Giudizio(G.CONFERMA, ms=5.0)


def nato(anni):
    return (datetime.date.today() - datetime.timedelta(days=anni * 366)).isoformat()


class Persone:
    def __init__(self):
        p = types.SimpleNamespace
        self.users = {
            "Carlo": p(name="Carlo", id="carlo", admin=False, preferred_voice=None,
                       preferred_tone=None),
            "Marta": p(name="Marta", id="marta", admin=True, preferred_voice=None,
                       preferred_tone=None),
            "Luca": p(name="Luca", id="luca", nascita=nato(12), tutori=["carlo"],
                      preferred_voice=None, preferred_tone=None)}

    def get(self, nome):
        return self.users.get(nome)

    def by_id(self, pid):
        return next((u for u in self.users.values() if u.id == pid), None)

    def embed(self, audio, sr):
        return None


class ChiParla:
    is_enrolling, enrolling_name, enroll_expired = False, None, False
    from_session = False
    compagnia = False

    def __init__(self):
        self.current_speaker, self.identified_by = None, None

    @property
    def current_level(self):
        return "familiare" if self.current_speaker else "ospite"


class Cervello:
    last_tools, last_private, on_tool_start, conv, turn_number = [], False, None, None, 0
    uso_precedente = last_context = last_compressione = last_lettura_s = None
    trattieni_schede = schede_attesa_ms = None

    def __init__(self):
        self.history = [{"role": "user", "content": "Mi aiuti con i compiti?"},
                        {"role": "assistant", "content": "Certo, dimmi l'esercizio."}]

    def stream_reply(self, text, level, context=None, **k):
        self.__dict__.pop("avvisi_turno", None)
        yield f"Risposta a «{text}»."

    def record_courtesy(self, a, b):
        pass

    def rilascia_schede(self, ok=True):
        self.trattieni_schede = None

    def record_interruption(self, played):
        pass

    def has_pending(self):
        return False

    def strip_tool_mentions(self, s):
        return s

    def mentions_tool(self, s):
        return False

    def redact(self, s):
        return s

    def rules_fired(self):
        return []

    def salva_conversazione(self):
        pass


class Hub:
    def __init__(self):
        self.schede = []

    def invia(self, scheda, mittente, forza=False):
        self.schede.append((mittente.persona, scheda))
        return {}


# ─────────────────────────── 1. l'anello ───────────────────────────
def prova_anello():
    c = Config()
    verifica("di serie: avvisi_audio spento, trascrizione accesa, 30 minuti, 16 MB, 20 s, 30 "
             "giorni", c.avvisi_audio is False and c.avvisi_trascrizione is True
             and c.avvisi_audio_anello_min == 30.0 and c.avvisi_audio_anello_mb == 16.0
             and c.avvisi_audio_contesto_s == 20.0 and c.avvisi_audio_giorni == 30.0)
    verifica("spento → nessun anello", AA.prepara(c) is None and AA.anello() is None)
    ora = [1000.0]
    an = AA.Anello(minuti=1.0, mb=0.2, orologio=lambda: ora[0])
    an.metti("turno:a", "luca", True, 990.0, 993.0, tono(3))
    an.metti("stanza:1", "carlo", False, 994.0, 996.0, tono(2))
    verifica("metti e prendi per luogo, persona e tempo",
             len(an.prendi()) == 2 and len(an.prendi(luogo="turno:a")) == 1
             and len(an.prendi(persona="carlo")) == 1 and an.prendi(da=995.0)[0].persona == "carlo"
             and not an.prendi(a=980.0))
    ora[0] = 1055.0
    verifica("oltre i minuti dell'anello i pezzi escono", len(an.prendi()) == 1)
    ora[0] = 1000.0
    for i in range(10):
        an.metti("turno:a", "luca", True, 1000.0 + i, 1003.0 + i, tono(3))
    st = an.stato()
    verifica("anello pieno: i più vecchi escono, entro il tetto in MB",
             st["mb"] <= 0.2 and an.buttati > 0 and an.prendi()[-1].inizio == 1009.0, str(st))
    verifica("«dimentica» di un luogo", an.togli(luogo="turno:a") > 0 and not an.prendi(
        luogo="turno:a"))
    an.metti("turno:a", "luca", True, 1000.0, 1002.0, tono(2))
    an.metti("turno:a", "luca", True, 1003.0, 1004.0, tono(1))
    p = os.path.join(CARTELLA, "prova.wav")
    with open(p, "wb") as fh:
        fh.write(AA.wav(an.prendi()))
    audio, sr = leggi_wav(p)
    verifica("WAV μ-law che si rilegge: i due pezzi con la pausa",
             sr == 16000 and abs(len(audio) / sr - 3.4) < 0.01, f"{len(audio) / sr}")
    verifica("contrario: frequenza diversa o vuoto non entrano",
             not an.metti("x", "luca", True, 0, 1, tono(1), sr=8000)
             and not an.metti("x", "luca", True, 0, 1, np.zeros(0, dtype=np.float32)))


# ─────────────────────────── 2. turni ───────────────────────────
def ciclo_di_prova(cfg, sottocartella):
    cart = os.path.join(CARTELLA, sottocartella)
    os.makedirs(cart, exist_ok=True)
    cfg.memory_db = os.path.join(cart, "memoria.db")
    persone = Persone()
    hub = Hub()
    minori.prepara(cfg, schermi=hub, registry=persone, log=lambda m: None)
    av = minori.avvisi()
    cas = Cassetto(cfg.memory_db, os.path.join(cart, "cassetto"), log=lambda m: None)
    av.cassetto = cas
    voce, cervello, chi = Voce(), Cervello(), ChiParla()
    ascolto = types.SimpleNamespace(started_at=0.0, ended_at=0.0, on_speech_start=None,
                                    on_speech_end=None)
    instr = types.SimpleNamespace(dopo_turno=lambda x: x, inizio_voce=lambda: None,
                                  persona=lambda *a: None, origine=lambda: {},
                                  annuncia_verso=lambda *a, **k: None,
                                  risposta_scritta=lambda *a: None)
    srv = Servizi(cfg, registry=persone, instradamento=instr, cortesia=Cortesia(),
                  turns=types.SimpleNamespace(write=lambda r: None),
                  attiva_minori=lambda: True, guardiano=Guardia(cfg), wake=object(),
                  barge_in=False, barge_voice=False)
    srv.controllo_impronte[0] = time.monotonic()
    annunci = types.SimpleNamespace(agenda=queue.Queue(), documenti=None, installazioni=None,
                                    lavori=None, estensioni=None)
    c = Ciclo(srv, corsie.Corsia("sat:telefono", nome="Telefono di Carlo"), ascolto, voce, chi,
              cervello, types.SimpleNamespace(), annunci, None, threading.Event())

    def turno(nome, testo, come="voce", audio=None, scritto=None):
        chi.current_speaker, chi.identified_by = nome, (come if nome else None)
        t = Turno(text=testo, speaker_name=nome, prof_turno=persone.get(nome), audio=audio,
                  scritto=scritto)
        c.rec = {}
        c._segna_minore(nome)
        c._anello_turno(t)
        n = len(voce.detto)
        if c._secondo_cancello(t) is not _FINE:
            c._rispondi(t)
            c._registra_risposta(t)
            c._dopo_la_risposta(t)
        return voce.detto[n:]
    return types.SimpleNamespace(c=c, av=av, cas=cas, hub=hub, voce=voce, turno=turno,
                                 persone=persone, chi=chi)


def prova_turni():
    cfg = Config()
    cfg.speaker_id_enabled = False
    cfg.uscita_controllo = False
    cfg.debug_audio_dir = None
    cfg.minori_pericolo_attesa_s = 0
    cfg.minori_avviso_ripetuto_s = 0
    cfg.minori_avviso_privato_s = 0
    cfg.avvisi_audio = True
    k = ciclo_di_prova(cfg, "turni")
    an = AA.anello()
    verifica("acceso: l'anello c'è", an is not None)
    k.turno("Carlo", "Che tempo fa?", audio=tono(2))
    verifica("contrario: l'audio di un adulto non entra nell'anello", not an.prendi())
    k.turno("Luca", "Che ore sono?", audio=tono(1.5), scritto={"testo": "Che ore sono?"})
    verifica("contrario: lo scritto non entra nell'anello", not an.prendi())
    k.turno("Luca", "Voglio farmi del male.", audio=tono(2.5))
    pezzi = an.prendi(persona="luca")
    verifica("l'audio del minore entra nell'anello (luogo della corsia)",
             len(pezzi) == 1 and pezzi[0].luogo == "turno:sat:telefono")
    riga = k.av.db.execute("SELECT trascrizione, audio, luogo, testo FROM avvisi_tutori WHERE "
                           "tutore = 'carlo' AND tipo = 'sicurezza'").fetchone()
    tr = json.loads(riga[0]) if riga and riga[0] else []
    verifica("acuto: la trascrizione con lo scambio di prima e la frase del segnale",
             [x["chi"] for x in tr] == ["Luca", "Calliope", "Luca"]
             and tr[-1]["testo"] == "Voglio farmi del male." and tr[-1]["segnale"]
             and not tr[0]["segnale"] and riga[2] == "turno:sat:telefono", str(tr))
    verifica("il testo dell'avviso resta senza parole", "Voglio farmi" not in riga[3], riga[3])
    f = k.cas.prendi("carlo", riga[1]) if riga[1] else None
    verifica("audio nel cassetto del tutore: fonte avviso, audio, scade fra 30 giorni",
             f is not None and f["fonte"] == "avviso" and f["categoria"] == "audio"
             and abs(f["scade"] - f["arrivato"] - 30 * 86400) < 5, str(f))
    dati = k.cas.byte(f) if f else b""
    p = os.path.join(CARTELLA, "turno.wav")
    open(p, "wb").write(dati)
    verifica("il file è il WAV dei segmenti del segnale (2,5 s)",
             abs(len(leggi_wav(p)[0]) / 16000 - 2.5) < 0.05)
    verifica("contrario: nessun audio nel cassetto di un adulto non tutore",
             not k.cas.elenco("marta"))
    schede = [(pid, s) for pid, s in k.hub.schede if s.get("tipo") == "avviso"]
    verifica("la scheda «avviso» solo al tutore, con trascrizione e «Scarica l'audio»",
             schede and all(pid == "carlo" for pid, _ in schede)
             and schede[-1][1]["trascrizione"][-1]["testo"] == "Voglio farmi del male."
             and schede[-1][1]["scarica"] == ["audio"] and schede[-1][1]["visibilita"]
             == "personale", str(schede[-1][1] if schede else None))
    scheda = schede[-1][1]
    verifica("il testo della scheda senza parole, con quando e da dove",
             "Voglio farmi" not in scheda["testo"] and "da una frase detta a me al telefono"
             in scheda["testo"])
    # «Scarica l'audio»: solo dal suo schermo personale
    sc = Scaricamenti(cfg)
    sc.registra(7, scheda, "carlo")
    g = sc.gettone({"id": 7, "proprietario": "carlo"}, scheda["chiave"], "audio")
    nome, tipo, byte = sc.prendi(g["url"].rsplit("/", 1)[1])
    verifica("Scarica l'audio dal suo schermo: un WAV", tipo == "audio/wav"
             and byte[:4] == b"RIFF" and nome.endswith(".wav"), nome)
    sc.registra(8, scheda, "carlo")
    try:
        sc.gettone({"id": 8, "proprietario": "marta"}, scheda["chiave"], "audio", amministra=True)
        rifiutato = False
    except Rifiuto as e:
        rifiutato = e.stato == 403
    verifica("contrario: un altro schermo personale, anche di chi amministra, no", rifiutato)
    try:
        sc.gettone({"id": 7, "proprietario": "carlo"}, scheda["chiave"], "md")
        md_no = False
    except Rifiuto:
        md_no = True
    verifica("contrario: la scheda dell'avviso non si scarica come testo", md_no)
    try:
        sc.gettone({"id": 7, "proprietario": None}, scheda["chiave"], "audio")
        stanza_no = False
    except Rifiuto:
        stanza_no = True
    verifica("contrario: uno schermo di stanza no", stanza_no)
    # A voce: la frase senza le parole
    k.av.db.execute("UPDATE avvisi_tutori SET detto = NULL WHERE tutore = 'carlo'")
    k.av.db.commit()
    k.chi.identified_by = "voce"
    detto = k.turno("Carlo", "Ci sei?")
    verifica("a voce mai le parole del minore", any("farsi del male" in x for x in detto)
             and not any("Voglio farmi" in x for x in detto), str(detto))
    verifica("la revisione del cassetto non conta l'audio dell'avviso",
             not k.cas.da_dire("carlo")["in_scadenza"])
    # Scadenza: il cassetto lo toglie in silenzio, la trascrizione esce con pulisci_materiale
    k.cas.ora = lambda: time.time() + 31 * 86400
    k.cas.pulisci()
    verifica("dopo 30 giorni l'audio non c'è più, senza «ho eliminato»",
             k.cas.prendi("carlo", riga[1]) is None and k.cas.da_dire("carlo")["eliminati"] == 0)
    k.cas.ora = time.time
    k.av.adesso = lambda: datetime.datetime.now() + datetime.timedelta(days=31)
    n = k.av.pulisci_materiale(forza=True)
    k.av.adesso = datetime.datetime.now
    verifica("dopo 30 giorni la trascrizione non c'è più (l'avviso resta)", n >= 1
             and k.av.db.execute("SELECT COUNT(*) FROM avvisi_tutori WHERE trascrizione IS NOT "
                                 "NULL").fetchone()[0] == 0
             and k.av.db.execute("SELECT COUNT(*) FROM avvisi_tutori").fetchone()[0] >= 1)

    # Spento l'audio: trascrizione sì, audio no; poi anche la trascrizione spenta
    cfg2 = Config()
    for a in ("speaker_id_enabled", "uscita_controllo"):
        setattr(cfg2, a, False)
    cfg2.debug_audio_dir = None
    cfg2.minori_pericolo_attesa_s = cfg2.minori_avviso_ripetuto_s = 0
    k2 = ciclo_di_prova(cfg2, "spento")
    k2.turno("Luca", "Voglio farmi del male.", audio=tono(2))
    r2 = k2.av.db.execute("SELECT trascrizione, audio FROM avvisi_tutori WHERE tutore = "
                          "'carlo'").fetchone()
    verifica("contrario: avvisi_audio spento → nessun anello né file, la trascrizione sì",
             AA.anello() is None and r2[0] and r2[1] is None and not k2.cas.elenco("carlo"),
             str(r2))
    cfg2.avvisi_trascrizione = False
    k2.c._cancelli().segnali.clear()
    k2.turno("Luca", "Voglio farmi del male, davvero.", audio=tono(2))
    r3 = k2.av.db.execute("SELECT trascrizione FROM avvisi_tutori WHERE tutore = 'carlo' "
                          "ORDER BY id DESC").fetchone()
    s3 = [s for _, s in k2.hub.schede][-1]
    verifica("contrario: avvisi_trascrizione false → niente trascrizione, né nella riga né nella "
             "scheda", r3[0] is None and "trascrizione" not in s3, str(s3))

    # conserva --svuota e «dimentica» delle conversazioni del tutore
    cfg.avvisi_audio = True
    k3 = ciclo_di_prova(cfg, "svuota")
    k3.turno("Luca", "Voglio farmi del male.", audio=tono(2))
    cons = Conservazione(cfg, k3.persone, log=lambda m: None)
    cons.avvisi = k3.av
    out = cons.svuota("luca", "Luca")
    verifica("conserva --svuota --persona (il minore): trascrizione e audio via",
             out["avvisi"] >= 1 and not k3.cas.elenco("carlo")
             and k3.av.db.execute("SELECT COUNT(*) FROM avvisi_tutori WHERE trascrizione IS NOT "
                                  "NULL").fetchone()[0] == 0, str(out))
    k3.c._cancelli().segnali.clear()
    k3.turno("Luca", "Voglio farmi del male, sul serio.", audio=tono(2))
    out = cons.svuota()
    verifica("conserva --svuota (tutto)", out["avvisi"] >= 1 and not k3.cas.elenco("carlo"))
    k3.c._cancelli().segnali.clear()
    k3.turno("Luca", "Voglio farmi del male, ancora.", audio=tono(2))
    n = k3.av.dimentica_materiale(tutore="marta")
    verifica("contrario: «dimentica» di un altro adulto non tocca gli avvisi del tutore",
             n == 0 and k3.cas.elenco("carlo"))
    verifica("«dimentica» del tutore: via", k3.av.dimentica_materiale(tutore="carlo") >= 1
             and not k3.cas.elenco("carlo"))
    # Da terminale: conserva --svuota senza Calliope accesa (il file e il cassetto)
    k3.c._cancelli().segnali.clear()
    k3.turno("Luca", "Voglio farmi del male, ancora una volta.", audio=tono(2))
    cfg.cassetto_cartella = os.path.join(CARTELLA, "svuota", "cassetto")
    cons2 = Conservazione(cfg, k3.persone, log=lambda m: None)
    out = cons2.svuota()
    verifica("conserva --svuota da terminale: anche il cassetto",
             out["avvisi"] >= 1 and not k3.cas.elenco("carlo"), str(out))


# ─────────────────────────── 3. stanza e guardiano ───────────────────────────
def prova_stanza():
    cfg = PSG.cfg_base(registro="aa1", stanza_guardia="attiva", avvisi_audio=True)
    AA.prepara(cfg)
    an = AA.anello()
    st = PSG.stanza_nuova(cfg)
    ORA = PSG.ORA
    seg = types.SimpleNamespace(sat=1, inizio_epoch=ORA - 5000, fine_epoch=ORA - 4997)
    carlo = {"chi": "persona:carlo-id", "persona": "carlo-id", "nome": "Carlo",
             "sicurezza": "voce", "minore": False}
    st._anello(seg, carlo, 1, tono(3))
    verifica("stanza, contrario: un adulto senza minori presenti non entra", not an.prendi())
    st._anello(seg, {"chi": "ignoto", "nome": None, "sicurezza": "nessuna"}, 2, tono(3))
    verifica("stanza, contrario: una voce non riconosciuta (ospite) non entra", not an.prendi())
    nicola = {"chi": "persona:nicola-id", "persona": "nicola-id", "nome": "Nicola",
              "sicurezza": "grigia", "minore": True}
    seg_n = types.SimpleNamespace(sat=1, inizio_epoch=ORA - 903, fine_epoch=ORA - 900)
    st._anello(seg_n, nicola, 3, tono(3))
    st._sentita("nicola-id", "Nicola", 1, ORA - 1000)
    seg_c = types.SimpleNamespace(sat=1, inizio_epoch=ORA - 913, fine_epoch=ORA - 910)
    st._anello(seg_c, carlo, 4, tono(3, 300))
    seg_lontano = types.SimpleNamespace(sat=1, inizio_epoch=ORA - 960, fine_epoch=ORA - 957)
    st._anello(seg_lontano, nicola, 5, tono(3))
    seg_altra = types.SimpleNamespace(sat=2, inizio_epoch=ORA - 903, fine_epoch=ORA - 900)
    st._anello(seg_altra, carlo, 6, tono(3))
    verifica("stanza: il minore (anche zona grigia) e l'adulto con il minore presente entrano; "
             "l'adulto in un'altra stanza no",
             [p.chiave for p in an.prendi()] == [5, 4, 3], str([p.chiave for p in an.prendi()]))
    st._anello(seg_altra, nicola, 7, tono(1))
    # Il guardiano in attiva: solo i segmenti del segnale col contesto breve
    hub = Hub()
    cart = os.path.join(CARTELLA, "guardia")
    os.makedirs(cart, exist_ok=True)
    av = minori.Avvisi(os.path.join(cart, "avvisi.db"), schermi=hub, registry=PSG.Voci(),
                       log=lambda m: None, cfg=cfg)
    av.cassetto = Cassetto(os.path.join(cart, "avvisi.db"), os.path.join(cart, "cassetto"),
                           log=lambda m: None)
    PSG.riga(st, 1, "Dai, giochiamo ancora una partita.", ORA - 910, "Carlo")
    PSG.riga(st, 1, "Il mister mi picchia quando sbaglio.", ORA - 900, "Nicola")
    g = PSG.guardia(cfg, st, avvisi=av)
    g.giro(ORA)
    r = av.db.execute("SELECT trascrizione, audio, luogo, testo FROM avvisi_tutori").fetchone()
    tr = json.loads(r[0]) if r and r[0] else []
    verifica("guardiano attivo: la trascrizione col contesto, chi ha detto cosa",
             [x["chi"] for x in tr] == ["Carlo", "Nicola (minore)"]
             and tr[1]["segnale"] and not tr[0]["segnale"]
             and "picchia" not in r[3] and r[2] == "stanza:1", str(tr))
    f = av.cassetto.prendi("carlo-id", r[1]) if r and r[1] else None
    p = os.path.join(CARTELLA, "guardia.wav")
    open(p, "wb").write(av.cassetto.byte(f) if f else b"")
    durata = len(leggi_wav(p)[0]) / 16000 if f else 0
    verifica("guardiano attivo: nel cassetto del tutore solo i segmenti del segnale col "
             "contesto (6 s + pausa), non quello di 45 s prima", abs(durata - 6.4) < 0.05,
             f"{durata}")
    verifica("la scheda del guardiano è «avviso», con la trascrizione",
             hub.schede and hub.schede[-1][1]["tipo"] == "avviso"
             and hub.schede[-1][0] == "carlo-id"
             and hub.schede[-1][1]["trascrizione"][1]["testo"].startswith("Il mister"))
    verifica("nel log e nelle misure mai le parole",
             "picchia" not in PSG.file_misure(cfg) and not any("picchia" in x for x in PSG.LOG))
    # Ombra: niente su disco, «audio_s» nelle misure
    cfg_o = PSG.cfg_base(registro="aa2", stanza_guardia="ombra", avvisi_audio=True)
    st_o = PSG.stanza_nuova(cfg_o)
    st_o._sentita("nicola-id", "Nicola", 1, ORA - 1000)
    AA.prepara(cfg_o)
    st_o._anello(seg_n, nicola, 3, tono(3))
    av_o = minori.Avvisi(os.path.join(cart, "ombra.db"), schermi=Hub(), registry=PSG.Voci(),
                         log=lambda m: None, cfg=cfg_o)
    av_o.cassetto = Cassetto(os.path.join(cart, "ombra.db"), os.path.join(cart, "cass-o"),
                             log=lambda m: None)
    PSG.riga(st_o, 1, "Il mister mi picchia quando sbaglio.", ORA - 900, "Nicola")
    g_o = PSG.guardia(cfg_o, st_o, avvisi=av_o)
    g_o.giro(ORA)
    m = [x for x in PSG.misure_guardia(cfg_o) if x.get("esito") == "giudicato"][-1]
    verifica("ombra: niente su disco, «avrei salvato 3 s» nelle misure",
             m.get("avviso") == "ombra" and m.get("audio_s") == 3.0
             and not av_o.cassetto.elenco("carlo-id")
             and not av_o.db.execute("SELECT COUNT(*) FROM avvisi_tutori").fetchone()[0], str(m))
    # «Dimentica» della stanza: l'anello di quel satellite e il materiale degli avvisi nati lì
    AA._ANELLO["anello"] = an
    minori._SERVIZIO["avvisi"] = av
    st.dimentica(1)
    verifica("«dimentica» della stanza: via l'audio nell'anello e trascrizione e audio "
             "dell'avviso nato lì", not an.prendi(luogo="stanza:1")
             and av.db.execute("SELECT trascrizione, audio FROM avvisi_tutori").fetchone()
             == (None, None) and not av.cassetto.elenco("carlo-id"))
    verifica("contrario: l'audio di un altro satellite resta", an.prendi(luogo="stanza:2"))


# ─────────────────────────── 4. un avviso di prima ───────────────────────────
def prova_avviso_di_prima():
    cfg = PSG.cfg_base(registro="aa3")
    hub = Hub()
    av = minori.Avvisi(os.path.join(CARTELLA, "prima.db"), schermi=hub, registry=PSG.Voci(),
                       log=lambda m: None, cfg=cfg)
    ora = datetime.datetime.fromtimestamp(PSG.ORA - 800).isoformat(timespec="seconds")
    av.db.execute("INSERT INTO avvisi_tutori (tutore, minore, tipo, testo, urgente, creato) "
                  "VALUES ('carlo-id', 'nicola-id', 'sicurezza_stanza', 'Da verificare.', 1, ?)",
                  (ora,))
    av.db.commit()
    d = av.da_dire("carlo-id", segna=False)[0]
    tutore = PSG.Voci().get("Carlo")
    av.scheda_di(tutore, d)
    s = hub.schede[-1][1]
    verifica("avviso di prima senza niente: la nota «non c'è più», nessuna trascrizione",
             "trascrizione" not in s and "non c'è più" in s.get("nota", ""), str(s))
    st = PSG.stanza_nuova(cfg)
    PSG.riga(st, 1, "Il mister mi picchia quando sbaglio.", PSG.ORA - 900, "Nicola")
    PSG.riga(st, 1, "Dai, giochiamo.", PSG.ORA - 905, "Carlo")
    av.trascrizione_dopo = lambda x: minori.ricostruisci_trascrizione(x, stanza=st,
                                                                      nome="Nicola")
    av.scheda_di(tutore, d)
    s = hub.schede[-1][1]
    verifica("avviso di prima: la trascrizione ricostruita dalla stanza (solo il minore), con "
             "la nota", [x["testo"] for x in s.get("trascrizione", [])]
             == ["Il mister mi picchia quando sbaglio."] and "Ricostruita" in s.get("nota", ""),
             str(s))
    verifica("la stessa chiave: la seconda scheda sostituisce la prima",
             hub.schede[-1][1]["chiave"] == hub.schede[-2][1]["chiave"])
    av.cfg.avvisi_trascrizione = False
    av.scheda_di(tutore, d)
    verifica("contrario: avvisi_trascrizione false → niente, nemmeno la nota",
             "trascrizione" not in hub.schede[-1][1] and "nota" not in hub.schede[-1][1])


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    for f in (prova_anello, prova_turni, prova_stanza, prova_avviso_di_prima):
        print(f"── {f.__name__}", flush=True)
        try:
            f()
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            verifica(f"{f.__name__} senza eccezioni", False, f"{type(e).__name__}: {e}")
    AA._ANELLO["anello"] = None
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}", flush=True)
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
