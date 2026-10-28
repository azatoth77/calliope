"""
Gli avvisi ai tutori con la data e l'origine (14/10/2026, calliope/minori.py `Avvisi`).

    python prove/prova_avvisi_data.py

Caso vero del 14/10: un avviso «sicurezza» urgente per il ragazzo, nato il 12/10 alle 19:02 (un
falso allarme, poi corretto nel codice), è rimasto da dire per due giorni (giustamente: il
ragazzo era vicino) ed è arrivato a chi amministra il 14/10 alle 9:11, sullo schermo del
telefono, **senza data**: preso per un allarme nuovo nato dalla conversazione della stanza;
Calliope, interrogata, non ne sapeva niente e ha confermato a caso. Qui, con un `Ciclo` con
voce, guardiano e Brain finti, avvisi veri su un database temporaneo e l'orologio fermo:

- un avviso di pochi minuti fa si dice senza data, con l'origine; uno vecchio con la data
  («ieri sera alle 19:02», «lunedì 12/10 alle 19:02»); la scheda ha sempre la data per intero;
- un avviso urgente rimasto da dire oltre `avvisi_urgente_ore` si dice «non più urgente», con
  la data (regola `avviso_urgente_scaduto`); un avviso segnato falso non si dice più (dal
  guardiano con `--falso`, o da `calliope stato --avvisi --falso`);
- vicino al minore resta la frase neutra (come dal 09/10) e i dati del turno non hanno l'avviso
  «sicurezza» di quel minore;
- un altro adulto, non tutore: niente avviso, niente nei dati del turno, niente dal tool;
- il tutore che chiede «cos'era quell'avviso?» ha nei dati del turno data, tipo, origine e
  stato veri; `minore_gestisci` azione `avvisi` li legge (con la voce, mai per un minore);
- l'origine resta con il segnale dei cancelli anche dopo un riavvio; un database di prima
  (senza le colonne nuove) si apre e si aggiorna.
Nomi di fantasia. Niente audio, modelli né rete: ~2 s.
"""
import datetime
import io
import os
import queue
import sqlite3
import sys
import tempfile
import threading
import time
import types
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope import cancelli as K, corsie, guardiano as G, minori  # noqa: E402
from calliope.ciclo import AVVISO_PRIVATO, Ciclo, Servizi, Turno, _FINE  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.cortesia import Cortesia  # noqa: E402

errori = 0
ADESSO = datetime.datetime(2026, 10, 14, 9, 11, 0)


def verifica(nome, cond, extra=""):
    global errori
    if not cond:
        errori += 1
    print(("ok  " if cond else "ERR ") + nome + (f"  ({extra})" if extra else ""), flush=True)


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
    def __init__(self, cfg):
        self.cfg = cfg

    def condivide_voce(self):
        return False

    timeout_s = 1.0

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
            "Carlo": p(name="Carlo", id="carlo", admin=True, preferred_voice=None,
                       preferred_tone=None),
            "Marta": p(name="Marta", id="marta", admin=False, preferred_voice=None,
                       preferred_tone=None),
            "Luca": p(name="Luca", id="luca", nascita=nato(12), tutori=["carlo"],
                      preferred_voice=None, preferred_tone=None)}

    def get(self, nome):
        return self.users.get(nome)

    def by_id(self, pid):
        return next((u for u in self.users.values() if u.id == pid), None)

    def find(self, nome):
        return nome if nome in self.users else None

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
        self.richieste, self.history, self.scambi, self.avvisi_visti = [], [], [], []

    def stream_reply(self, text, level, context=None, **k):
        self.richieste.append(text)
        self.avvisi_visti.append(self.__dict__.pop("avvisi_turno", None))
        yield f"Risposta a «{text}»."

    def record_courtesy(self, a, b):
        self.scambi.append((a, b))

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


def main():
    cfg = Config()
    cfg.speaker_id_enabled = False
    cfg.uscita_controllo = False
    cfg.debug_audio_dir = None
    cfg.minori_pericolo_attesa_s = 0
    cfg.minori_avviso_ripetuto_s = 0
    cartella = tempfile.mkdtemp(prefix="calliope-avvisi-data-")
    cfg.memory_db = os.path.join(cartella, "memoria.db")
    persone = Persone()
    hub = Hub()
    log = []
    minori.prepara(cfg, schermi=hub, registry=persone, log=log.append)
    av = minori.avvisi()
    av.adesso = lambda: ADESSO
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

    def turno(nome, testo, come="voce"):
        chi.current_speaker, chi.identified_by = nome, (come if nome else None)
        t = Turno(text=testo, speaker_name=nome, prof_turno=persone.get(nome))
        c.rec = {}
        c._segna_minore(nome)
        n = len(voce.detto)
        if c._secondo_cancello(t) is not _FINE:
            c._rispondi(t)
            c._registra_risposta(t)
            c._dopo_la_risposta(t)
        return voce.detto[n:], c.rec.get("regole", [])

    def metti(tipo, testo, creato, urgente=True, origine="da una frase detta a me al telefono",
              rif=None, detto=None, come=None, tutore="carlo"):
        cur = av.db.execute("INSERT INTO avvisi_tutori (tutore, minore, tipo, testo, urgente, "
                            "creato, origine, rif, detto, come) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (tutore, "luca", tipo, testo, int(urgente), creato, origine,
                             rif or f"prova:{creato}", detto, come))
        av.db.commit()
        return cur.lastrowid

    def pulisci():
        av.db.execute("DELETE FROM avvisi_tutori")
        av.db.commit()
        cervello.avvisi_visti.clear()
        c._minori_sentiti.clear()
        c._avvisi_accennati.clear()

    # ── 1. quando_nato ──
    verifica("pochi minuti fa: nessuna data",
             minori.quando_nato("2026-10-14T09:05:00", ADESSO) == "")
    verifica("oggi, ieri sera, un giorno della settimana con la data",
             minori.quando_nato("2026-10-14T07:02:00", ADESSO) == "oggi alle 7:02"
             and minori.quando_nato("2026-10-13T19:02:00", ADESSO) == "ieri sera alle 19:02"
             and minori.quando_nato("2026-10-12T19:02:00", ADESSO) == "lunedì 12/10 alle 19:02")
    verifica("origine in parole semplici",
             minori.origine_turno("Telefono di Carlo", "sat:telefono")
             == "da una frase detta a me al telefono"
             and minori.origine_turno("cucina", "sat:3") == "da una frase detta a me dal "
                                                            "satellite cucina"
             and minori.origine_turno(None, "locale") == "da una frase detta a me"
             and minori.origine_turno("x", "sat:1", scritto=True).startswith("da una frase "
                                                                             "scritta")
             and minori.origine_stanza("cucina") == "dalla rilettura della conversazione in "
                                                    "cucina")

    # ── 2. un avviso fresco: senza data, con l'origine; la scheda con la data ──
    prof_l = persone.get("Luca")
    av.manda(prof_l, "sicurezza", "Segnale confermato: Luca ha parlato di farsi del male.",
             urgente=True, origine="da una frase detta a me al telefono")
    scheda = hub.schede[-1][1]
    verifica("la scheda ha sempre quando è nato (per intero) e da dove",
             "Mercoledì 14/10 alle 9:11, da una frase detta a me al telefono." in scheda["testo"]
             and hub.schede[-1][0] == "carlo", scheda["testo"])
    detto, regole = turno("Carlo", "Che tempo fa domani?")
    verifica("fresco: a voce senza data, con l'origine",
             any("Ho un avviso per te, da una frase detta a me al telefono: Segnale confermato"
                 in x for x in detto) and "avviso_con_data" not in regole
             and "avviso_urgente_scaduto" not in regole, f"{detto} {regole}")
    riga = av.db.execute("SELECT come, detto FROM avvisi_tutori").fetchone()
    verifica("consegnato: come = voce, con l'ora", riga == ("voce", "2026-10-14T09:11:00"),
             str(riga))

    # ── 3. il caso vero: urgente, del 12/10 alle 19:02, rimasto da dire ──
    pulisci()
    metti("sicurezza", "Segnale confermato: Luca ha parlato di farsi del male.",
          "2026-10-12T19:02:00")
    # Il ragazzo ha parlato da poco qui: resta la frase neutra (come dal 09/10)
    turno("Luca", "Che ore sono?")
    detto, regole = turno("Carlo", "Che tempo fa domani?")
    verifica("contrario: minore vicino → frase neutra, niente data né testo a voce",
             any(AVVISO_PRIVATO in x for x in detto)
             and not any("farsi del male" in x for x in detto)
             and "avviso_sicurezza_rinviato" in regole, f"{detto} {regole}")
    c._minori_sentiti["luca"] -= cfg.minori_avviso_privato_s + 1
    detto, regole = turno("Carlo", "Ci sei ancora?")
    frase = next((x for x in detto if "farsi del male" in x), "")
    verifica("vecchio: «non più urgente», con la data e l'origine",
             frase.startswith("Ho un avviso per te, non più urgente, nato lunedì 12/10 alle "
                              "19:02, da una frase detta a me al telefono: Segnale confermato")
             and "avviso_urgente_scaduto" in regole and "avviso_con_data" in regole,
             f"{frase!r} {regole}")
    # Ieri sera, non urgente: la data, nessun «non più urgente»
    pulisci()
    metti("gioco", "Luca ha chiesto mezz'ora di gioco in più.", "2026-10-13T19:02:00",
          urgente=False, origine="")
    detto, regole = turno("Carlo", "Novità per me?")
    verifica("non urgente di ieri sera: la data, nessun «non più urgente»",
             any(x.startswith("Ho un avviso per te, nato ieri sera alle 19:02: Luca ha chiesto")
                 for x in detto) and "avviso_urgente_scaduto" not in regole, str(detto))
    # Urgente di 3 ore fa (sotto la soglia di 12): resta urgente, con la data
    pulisci()
    metti("sicurezza", "Segnale confermato: Luca ha parlato di farsi del male.",
          "2026-10-14T06:10:00")
    d = av.da_dire("carlo", segna=False)
    verifica("contrario: urgente di 3 ore fa resta urgente (sotto avvisi_urgente_ore)",
             d and d[0]["urgente"] and not d[0]["scaduto"], str(d))
    cfg.avvisi_urgente_ore = 0
    metti("sicurezza", "Vecchio.", "2026-10-10T06:10:00")
    verifica("contrario: avvisi_urgente_ore = 0 → resta urgente sempre",
             all(x["urgente"] for x in av.da_dire("carlo", segna=False)))
    cfg.avvisi_urgente_ore = 12.0

    # ── 4. segnato falso: non si dice più ──
    pulisci()
    metti("sicurezza_stanza", "Da verificare, sentito in cucina.", "2026-10-13T19:02:00",
          rif="guardia:1013-190200", origine="dalla rilettura della conversazione in cucina")
    metti("compiti", "Luca ha chiesto aiuto.", "2026-10-14T09:00:00", urgente=False,
          origine="")
    verifica("segna_falso dal riferimento del guardiano", av.segna_falso("guardia:1013-190200")
             == 1)
    detto, regole = turno("Carlo", "Ci sono novità?")
    verifica("l'avviso falso non si dice, l'altro sì",
             not any("cucina" in x for x in detto) and any("aiuto" in x for x in detto)
             and av.db.execute("SELECT come FROM avvisi_tutori WHERE rif = "
                               "'guardia:1013-190200'").fetchone()[0] == "falso",
             str(detto))
    # Da terminale: calliope stato --avvisi e --falso
    from calliope import stato as stato_mod
    aid = metti("sicurezza", "Segnale confermato: prova.", "2026-10-12T19:02:00",
                rif="av:luca:2026-10-12T19:02:00:sicurezza")
    metti("sicurezza", "Segnale confermato: prova.", "2026-10-12T19:02:00", tutore="marta",
          rif="av:luca:2026-10-12T19:02:00:sicurezza")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = stato_mod.avvisi_main(cfg, ["--avvisi", "--falso", f"AV{aid}"], False)
    verifica("stato --avvisi --falso: tutte le righe dei tutori di quell'avviso",
             rc == 0 and "2 righe" in buf.getvalue()
             and not any(x["id"] == aid for x in av.da_dire("carlo", segna=False)),
             buf.getvalue())
    buf = io.StringIO()
    with redirect_stdout(buf):
        stato_mod.avvisi_main(cfg, ["--avvisi", "--giorni", "3650"], False)
    verifica("stato --avvisi elenca con l'origine e FALSO",
             "FALSO" in buf.getvalue() and "rilettura della conversazione in cucina"
             in buf.getvalue() and "farsi del male" not in buf.getvalue(), buf.getvalue())

    # ── 5. il tutore chiede: i dati del turno hanno gli avvisi consegnati ──
    pulisci()
    metti("sicurezza", "Segnale confermato: Luca ha parlato di farsi del male.",
          "2026-10-12T19:02:00", detto="2026-10-14T09:11:00", come="schermo")
    turno("Carlo", "Cos'era quell'avviso sul telefono?")
    blocco = cervello.avvisi_visti[-1] or ""
    verifica("domanda del tutore: nei dati del turno data, tipo, origine, come e stato",
             "nato lunedì 12/10 alle 19:02" in blocco and "tipo sicurezza" in blocco
             and "per Luca" in blocco and "da una frase detta a me al telefono" in blocco
             and "sullo schermo oggi alle 9:11" in blocco and "urgente" in blocco
             and "non inventare" in blocco, blocco)
    verifica("regola avvisi_nel_turno", "avvisi_nel_turno" in c.rec.get("regole", []))
    turno("Marta", "Cos'era quell'avviso sul telefono?")
    verifica("contrario: altro adulto non tutore → niente nei dati del turno",
             cervello.avvisi_visti[-1] is None)
    chi_brevi = turno
    chi_brevi("Carlo", "Cos'era?", come="breve")
    verifica("contrario: tutore non riconosciuto dalla voce → niente",
             cervello.avvisi_visti[-1] is None)
    turno("Luca", "Cos'era quell'avviso?")
    verifica("contrario: il minore stesso → niente", cervello.avvisi_visti[-1] is None)
    # Il minore ha parlato da poco qui: l'avviso «sicurezza» resta fuori, con la riga riservata
    turno("Carlo", "Cos'era quell'avviso?")
    blocco = cervello.avvisi_visti[-1] or ""
    verifica("contrario: minore vicino → l'avviso sicurezza fuori dai dati del turno",
             "farsi del male" not in blocco and "riservato" in blocco, blocco)
    c._minori_sentiti.clear()
    cfg.avvisi_contesto_ore = 0
    turno("Carlo", "Cos'era quell'avviso?")
    verifica("contrario: avvisi_contesto_ore = 0 → mai nel turno",
             cervello.avvisi_visti[-1] is None)
    cfg.avvisi_contesto_ore = 48.0
    metti("compiti", "Vecchio di un mese.", "2026-09-01T10:00:00", urgente=False,
          detto="2026-09-01T10:05:00", come="voce")
    turno("Carlo", "Cos'era quell'avviso?")
    verifica("contrario: un avviso consegnato un mese fa non è nei dati del turno",
             "Vecchio di un mese" not in (cervello.avvisi_visti[-1] or ""))

    # ── 6. il tool minore_gestisci azione avvisi ──
    from calliope.tools import minori as TM
    ctx = types.SimpleNamespace(speakers=persone, speaker_ctx=types.SimpleNamespace(
        identified_by="voce", current_speaker="Carlo"), regole=[], rules=[])
    orig = minori.profilo
    minori.profilo = lambda ctx_: persone.get(ctx_.speaker_ctx.current_speaker)
    try:
        r = TM._minore_gestisci(ctx, nome="Luca", azione="avvisi")
        verifica("tool: il tutore con la voce legge gli avvisi con data e origine",
                 r.get("ok") and any("nato lunedì 12/10 alle 19:02" in x for x in r["avvisi"])
                 and "non inventare" in r["cosa_fare"], str(r))
        ctx.speaker_ctx.current_speaker = "Marta"
        r = TM._minore_gestisci(ctx, azione="avvisi")
        verifica("tool, contrario: altro adulto non tutore → nessun avviso",
                 "non ti ho consegnato avvisi" in str(r.get("risposta_finale") or r), str(r))
        ctx.speaker_ctx.current_speaker = "Luca"
        r = TM._minore_gestisci(ctx, azione="avvisi")
        verifica("tool, contrario: il minore → no", not r.get("ok"), str(r))
        ctx.speaker_ctx.current_speaker, ctx.speaker_ctx.identified_by = "Carlo", "breve"
        r = TM._minore_gestisci(ctx, azione="avvisi")
        verifica("tool, contrario: senza la voce riconosciuta → no", not r.get("ok"), str(r))
    finally:
        minori.profilo = orig

    # ── 7. cancelli: l'origine nell'avviso e dopo un riavvio ──
    pulisci()
    av.adesso = datetime.datetime.now
    turno("Luca", "Voglio farmi del male.")
    row = av.db.execute("SELECT origine, urgente FROM avvisi_tutori WHERE minore = 'luca' AND "
                        "tipo = 'sicurezza'").fetchone()
    verifica("acuto dal telefono: l'avviso ha l'origine «al telefono»",
             row == ("da una frase detta a me al telefono", 1), str(row))
    p = os.path.join(cartella, "cancelli.json")
    k = K.Cancelli(cfg, log=lambda m: None, percorso=p)
    s = k.apri(prof_l, "boh", ("autolesionismo",), False, "sat:telefono",
               origine="da una frase detta a me al telefono")
    k2 = K.Cancelli(cfg, log=lambda m: None, percorso=p)
    verifica("l'origine del segnale resta dopo un riavvio (senza il testo)",
             k2.segnali and k2.segnali[-1].origine == "da una frase detta a me al telefono"
             and "boh" not in open(p, encoding="utf-8").read(), str(k2.segnali))
    del s

    # ── 8. un database di prima ──
    vecchio = os.path.join(cartella, "vecchio.db")
    db = sqlite3.connect(vecchio)
    db.execute("CREATE TABLE avvisi_tutori (id INTEGER PRIMARY KEY, tutore TEXT NOT NULL, "
               "minore TEXT NOT NULL, tipo TEXT NOT NULL, testo TEXT NOT NULL, urgente INTEGER "
               "NOT NULL DEFAULT 0, creato TEXT NOT NULL, detto TEXT)")
    db.execute("INSERT INTO avvisi_tutori (tutore, minore, tipo, testo, urgente, creato) VALUES "
               "('carlo', 'luca', 'sicurezza', 'Vecchio avviso.', 1, '2026-10-12T19:02:00')")
    db.commit()
    db.close()
    av2 = minori.Avvisi(vecchio, log=lambda m: None, cfg=cfg)
    av2.adesso = lambda: ADESSO
    d = av2.da_dire("carlo", segna=False)
    verifica("database di prima: si apre, l'avviso vecchio si dice non urgente con la data",
             av2.scrivibile and d and d[0]["scaduto"] and "nato lunedì 12/10 alle 19:02"
             in av2.frase(d) and d[0]["origine"] == "", av2.frase(d))
    av2.close()

    for r in minori._SERVIZIO.values():
        try:
            r.db.close()
        except Exception:  # noqa: BLE001
            pass
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
