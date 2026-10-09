"""
Il giro a due cancelli per un minore che forse è in pericolo (09/10/2026, calliope/cancelli.py).

    python prove/prova_minori_cancelli.py

Caso vero sulla DGX dell'08/10: un adulto ospite preso per il ragazzo (voce incerta) dice una
frase di 0,6 s (un saluto) e il rilevatore dice «pericolo»: protezione con 19696 e 112 e avviso
«sicurezza» al tutore, ma il ragazzo non c'era. Ora un segnale poco chiaro passa da due
cancelli: una frase che rassicura e chiede, poi la risposta torna al rilevatore. Un `Ciclo` con
voce, guardiano (con `gravita` e `verifica` finti) e Brain finti, avvisi veri su un database
temporaneo:

- acuto ed esplicito: protezione e avviso urgente subito, come prima («Segnale confermato»);
- il caso vero riscritto: «Addio.» con la voce incerta → rassicura (ragazzi), nessun avviso;
  la risposta dell'ospite sullo stesso satellite lo smentisce → risposta normale, nessun avviso;
- conferma al secondo cancello → protezione e avviso urgente con i due passaggi, senza il
  modello; un giudizio guasto vale conferma;
- smentita e poi un secondo segnale poco chiaro nella finestra → confermato subito;
- silenzio: avviso non urgente «da verificare» (e niente con `minori_pericolo_silenzio: niente`);
- voce incerta su un segnale acuto: protezione e avviso che lo dice;
- con la voce sicura del minore la frase di un'altra persona non chiude il cancello;
- gravità guasta = acuto; `minori_pericolo_verifica: false` = come prima; ospiti invariati;
- un avviso «sicurezza» non si dice a voce al tutore dove il minore ha parlato da poco
  (`avviso_sicurezza_rinviato`); contrari: finestra passata, avviso di altro tipo.
I contrari del pericolo con la frase spezzata restano in `prova_minori_pericolo.py`, invariata.
Niente audio, modelli né rete: ~3 s.
"""
import concurrent.futures
import datetime
import os
import queue
import sys
import tempfile
import threading
import time
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calliope import cancelli as K, corsie, guardiano as G, minori  # noqa: E402
from calliope.ciclo import AVVISO_PRIVATO, Ciclo, Servizi, Turno, _FINE  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.cortesia import Cortesia  # noqa: E402

errori = 0


def verifica(nome, cond, extra=""):
    global errori
    if not cond:
        errori += 1
    print(("ok  " if cond else "ERR ") + nome + (f"  ({extra})" if extra else ""), flush=True)


class Voce:
    muto, _current_voice_path, on_parla, interrupted = False, "", None, False

    def __init__(self):
        self.detto, self.played = [], []

    def say(self, t):
        self.detto.append(t)
        self.played.append(t)
    say_cached = say

    def saying_name(self):
        return False

    def wait(self, *a):
        return True

    def interrupt(self):
        pass

    def start_turn(self):
        self.played = []

    def chime(self, *a):
        pass
    suono_ascolto = prepare = change_voice = chime


class Guardia:
    """Il guardiano finto. Pericolo sulla domanda: «addio», «sparisco», «farmi del male»,
    «aiuto». Gravità: acuto con «male», guasto con «GUASTA», altrimenti dubbio. Verifica:
    smentita con «tutto bene», «salutavo», «che ore»; guasto con «GUASTA»; altrimenti conferma."""
    timeout_s = 1.0

    def __init__(self, cfg):
        self.cfg, self.gravita_chieste, self.verifiche = cfg, [], []

    def condivide_voce(self):
        return False

    def in_parallelo(self, domanda, frase, categorie):
        f = concurrent.futures.Future()
        d = domanda.lower()
        if frase is None and any(k in d for k in ("addio", "sparisco", "farmi del male",
                                                   "aiuto")):
            f.set_result(G.Giudizio(G.PERICOLO, ("autolesionismo",) if "male" in d
                                    else ("pericolo",)))
        else:
            f.set_result(G.Giudizio(G.OK))
        return f

    def gravita(self, frase):
        self.gravita_chieste.append(frase)
        if "GUASTA" in frase:
            return G.Giudizio(G.GUASTO, grezzo="timeout")
        return G.Giudizio(G.ACUTO if "male" in frase.lower() else G.DUBBIO, ms=5.0)

    def verifica(self, primo, risposta):
        self.verifiche.append((primo, risposta))
        r = risposta.lower()
        if "guasta" in r:
            return G.Giudizio(G.GUASTO, grezzo="timeout")
        if any(k in r for k in ("tutto bene", "salutavo", "che ore")):
            return G.Giudizio(G.SMENTITA, ms=5.0)
        return G.Giudizio(G.CONFERMA, ms=5.0)


def nato(anni):
    return (datetime.date.today() - datetime.timedelta(days=anni * 366)).isoformat()


class Persone:
    def __init__(self):
        p = types.SimpleNamespace
        self.users = {
            "Carlo": p(name="Carlo", id="carlo", admin=True, preferred_voice=None,
                       preferred_tone=None),
            "Sofia": p(name="Sofia", id="sofia", nascita=nato(9), tutori=["carlo"],
                       preferred_voice=None, preferred_tone=None),
            "Tommaso": p(name="Tommaso", id="tommaso", nascita=nato(12), tutori=["carlo"],
                          preferred_voice=None, preferred_tone=None),
            "Luca": p(name="Luca", id="luca", nascita=nato(8), tutori=["carlo"],
                      preferred_voice=None, preferred_tone=None)}

    def get(self, nome):
        return self.users.get(nome)

    def embed(self, audio, sr):
        return None

    def best_match(self, emb=None):
        return "Sofia", 0.70


class ChiParla:
    is_enrolling, enrolling_name, enroll_expired = False, None, False
    from_session = False

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
        self.richieste, self.history, self.scambi = [], [], []

    def stream_reply(self, text, level, context=None, **k):
        self.richieste.append(text)
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


def main():
    cfg = Config()
    cfg.speaker_id_enabled = False
    cfg.uscita_controllo = False
    cfg.debug_audio_dir = None
    cfg.minori_pericolo_attesa_s = 0           # niente timer: il silenzio si chiama a mano
    cartella = tempfile.mkdtemp(prefix="calliope-cancelli-")
    cfg.memory_db = os.path.join(cartella, "memoria.db")
    persone = Persone()
    righe, registro = [], []
    minori.prepara(cfg, registry=persone, log=lambda m: righe.append(m))
    av = minori.avvisi()
    voce, cervello, chi = Voce(), Cervello(), ChiParla()
    ascolto = types.SimpleNamespace(started_at=0.0, ended_at=0.0, on_speech_start=None,
                                    on_speech_end=None)
    instr = types.SimpleNamespace(dopo_turno=lambda x: x, inizio_voce=lambda: None,
                                  persona=lambda *a: None, origine=lambda: {},
                                  annuncia_verso=lambda *a, **k: None,
                                  risposta_scritta=lambda *a: None)
    guardia = Guardia(cfg)
    srv = Servizi(cfg, registry=persone, instradamento=instr, cortesia=Cortesia(),
                  turns=types.SimpleNamespace(write=registro.append),
                  attiva_minori=lambda: True, guardiano=guardia, wake=object(),
                  barge_in=False, barge_voice=False)
    srv.controllo_impronte[0] = time.monotonic()
    annunci = types.SimpleNamespace(agenda=queue.Queue(), documenti=None, installazioni=None,
                                    lavori=None, estensioni=None)
    c = Ciclo(srv, corsie.Corsia("sat:telefono"), ascolto, voce, chi, cervello,
              types.SimpleNamespace(), annunci, None, threading.Event())

    def turno(nome, testo, come="voce"):
        """Un turno dalla fase del secondo cancello alla fine (come `giro`)."""
        chi.current_speaker, chi.identified_by = nome, (come if nome else None)
        t = Turno(text=testo, speaker_name=nome, prof_turno=persone.get(nome))
        c.rec = {}
        c._segna_minore(nome)
        n, nr = len(voce.detto), len(cervello.richieste)
        if c._secondo_cancello(t) is not _FINE:
            c._rispondi(t)
            c._registra_risposta(t)
            c._dopo_la_risposta(t)
        return (voce.detto[n:], c.rec.get("regole", []), c.rec,
                len(cervello.richieste) > nr)

    def avvisi_di(minore):
        return av.db.execute("SELECT testo, urgente, detto FROM avvisi_tutori WHERE minore = ? "
                             "AND tipo = 'sicurezza' AND tutore = 'carlo' ORDER BY id",
                             (minore,)).fetchall()

    prot = G.PROTEZIONE

    # 1. Acuto ed esplicito, voce sicura: come prima
    detto, regole, rec, _ = turno("Sofia", "Calliope, voglio farmi del male.")
    a = avvisi_di("sofia")
    verifica("acuto: protezione e avviso urgente subito",
             detto == [prot] and len(a) == 1 and a[0][1] == 1
             and a[0][0].startswith("Segnale confermato: Sofia ha parlato di farsi del male")
             and "pericolo_acuto" in regole, f"{detto} {a} {regole}")
    verifica("acuto: nessun segnale aperto, livello confermato nel registro",
             srv.cancelli.aperto_per("sofia", "sat:telefono") is None
             and rec.get("pericolo", {}).get("livello") == "confermato"
             and rec.get("testo") is None, str(rec.get("pericolo")))
    verifica("acuto con la voce sicura: l'avviso non parla della voce",
             "voce non era sicura" not in a[0][0], a[0][0])

    # 2. Il caso vero riscritto: «Addio.» con la voce incerta (frase breve), poi l'ospite
    detto, regole, rec, modello = turno("Tommaso", "Addio.", come="breve")
    verifica("caso vero: «Addio.» con la voce incerta → rassicura per ragazzi, nessun avviso",
             detto == [K.RASSICURA["ragazzi"]] and not avvisi_di("tommaso")
             and "pericolo_da_verificare" in regole and "pericolo_voce_incerta" in regole,
             f"{detto} {regole}")
    verifica("cancello 1: niente testo del minore nel registro, livello da verificare",
             rec.get("testo") is None and rec.get("richiesta") is None
             and rec["pericolo"]["livello"] == "da_verificare"
             and rec["guardiano"].get("esito") == "pericolo", str(rec.get("pericolo")))
    verifica("la frase che rassicura non nomina l'allarme né i numeri",
             all(x not in detto[0].lower() for x in ("pericolo", "allarme", "avviso", "19696",
                                                      "112")), detto[0])
    detto, regole, rec, modello = turno(None, "Sì sì tutto bene, salutavo un amico.",
                                        come=None)
    verifica("caso vero: la risposta dell'ospite sullo stesso satellite smentisce → risposta "
             "normale, nessun avviso",
             modello and prot not in detto and not avvisi_di("tommaso")
             and "pericolo_smentito" in regole and rec["pericolo"]["esito"] == "smentita"
             and guardia.verifiche[-1][0] == "Addio.", f"{detto} {regole}")
    verifica("smentito: il segnale non è più aperto",
             srv.cancelli.aperto_per("tommaso", "sat:telefono") is None)

    # 2b. Voce incerta: un adulto riconosciuto con sicurezza sullo stesso satellite non chiude
    srv.cancelli.segnali.clear()               # il segnale smentito sopra non conta qui
    turno("Tommaso", "Addio.", come="breve")
    detto, regole, rec, modello = turno("Carlo", "Che ore sono?")
    verifica("contrario: con la voce incerta un adulto sicuro sullo stesso satellite non "
             "chiude il cancello", modello and "pericolo_smentito" not in regole
             and srv.cancelli.aperto_per("tommaso", "sat:telefono") is not None, str(regole))
    detto, regole, rec, modello = turno("Tommaso", "Tutto bene, era un saluto.", come="breve")
    verifica("poi la frase attribuita al ragazzo lo chiude", "pericolo_smentito" in regole
             and not avvisi_di("tommaso"), str(regole))
    srv.cancelli.segnali.clear()

    # 3. Conferma al secondo cancello (voce sicura)
    c.rec = {}
    detto, regole, rec, _ = turno("Luca", "Sparisco.")
    verifica("Luca «Sparisco.»: rassicura per bambini", detto == [K.RASSICURA["bambini"]]
             and not avvisi_di("luca"), str(detto))
    detto, regole, rec, modello = turno("Luca", "Non posso dirlo.")
    a = avvisi_di("luca")
    verifica("conferma al secondo cancello: protezione senza il modello, avviso urgente",
             detto == [prot] and not modello and len(a) == 1 and a[0][1] == 1
             and "la risposta ha confermato" in a[0][0] and "pericolo_confermato" in regole
             and rec.get("esito") == "protezione" and rec.get("testo") is None,
             f"{detto} {a} {regole}")
    verifica("conferma: lo scambio chiuso resta nella storia del modello",
             cervello.scambi[-1] == ("Non posso dirlo.", prot), str(cervello.scambi[-1:]))
    verifica("l'avviso non contiene le parole del minore",
             "posso dirlo" not in a[0][0] and "Sparisco" not in a[0][0], a[0][0])

    # 4. Con la voce sicura la frase di un'altra persona non chiude il cancello
    turno("Sofia", "Sparisco.")
    detto, regole, rec, modello = turno("Carlo", "Che ore sono?")
    verifica("contrario: un adulto sicuro risponde al posto del minore → il cancello resta "
             "aperto", modello and "pericolo_smentito" not in regole
             and srv.cancelli.aperto_per("sofia", "sat:telefono") is not None, str(regole))
    detto, regole, rec, modello = turno("Sofia", "Sì, tutto bene, giocavo.")
    verifica("poi la risposta di Sofia lo chiude (smentita)",
             "pericolo_smentito" in regole and len(avvisi_di("sofia")) == 1, str(regole))

    # 5. Un secondo segnale poco chiaro nella finestra → confermato subito
    detto, regole, rec, _ = turno("Sofia", "Aiuto.")
    a = avvisi_di("sofia")
    verifica("due segnali poco chiari ravvicinati → protezione e avviso",
             detto == [prot] and len(a) == 2 and "secondo segnale" in a[-1][0]
             and "pericolo_secondo_segnale" in regole, f"{detto} {regole}")
    verifica("il secondo segnale non chiede la gravità (decide la finestra)",
             guardia.gravita_chieste[-1] != "Aiuto.", str(guardia.gravita_chieste[-1:]))

    # 6. Silenzio: nessuna risposta entro l'attesa
    srv.cancelli.segnali.clear()
    detto, regole, rec, _ = turno("Tommaso", "Addio.", come="conversazione")
    seg = srv.cancelli.aperto_per("tommaso", "sat:telefono")
    n_reg = len(registro)
    verifica("silenzio: il segnale è aperto", seg is not None and seg.voce_incerta)
    partito = srv.cancelli.scaduto(seg)
    a = avvisi_di("tommaso")
    verifica("silenzio → avviso NON urgente «da verificare», con la voce non sicura",
             partito and len(a) == 1 and a[0][1] == 0 and a[0][0].startswith("Da verificare")
             and "voce non era sicura" in a[0][0] and "Addio" not in a[0][0], str(a))
    verifica("silenzio: una riga nel registro dei turni senza testo",
             len(registro) == n_reg + 1 and registro[-1]["esito"] == "pericolo_silenzio"
             and "testo" not in registro[-1], str(registro[-1:]))
    verifica("silenzio: chiamato due volte non manda due avvisi",
             srv.cancelli.scaduto(seg) is False and len(avvisi_di("tommaso")) == 1)
    srv.cancelli.segnali.clear()
    cfg.minori_pericolo_silenzio = "niente"
    turno("Luca", "Addio.")
    seg = srv.cancelli.aperto_per("luca", "sat:telefono")
    verifica("contrario: minori_pericolo_silenzio «niente» → nessun avviso",
             srv.cancelli.scaduto(seg) is False and len(avvisi_di("luca")) == 1)
    cfg.minori_pericolo_silenzio = "avvisa"
    srv.cancelli.segnali.clear()

    # 7. Timer vero dell'attesa (breve)
    cfg.minori_pericolo_attesa_s = 0.2
    turno("Luca", "Addio.")
    time.sleep(0.6)
    a = avvisi_di("luca")
    verifica("l'attesa scade da sola: avviso da verificare",
             len(a) == 2 and a[-1][0].startswith("Da verificare"), str(a[-1:]))
    cfg.minori_pericolo_attesa_s = 0
    srv.cancelli.segnali.clear()

    # 8. Voce incerta su un segnale acuto: protezione e avviso che lo dice
    detto, regole, rec, _ = turno("Tommaso", "Voglio farmi del male.", come="conversazione")
    a = avvisi_di("tommaso")
    verifica("acuto con la voce incerta: protezione e avviso urgente «la voce non era sicura»",
             detto == [prot] and a[-1][1] == 1 and "voce non era sicura" in a[-1][0]
             and "pericolo_voce_incerta" in regole, f"{a[-1:]} {regole}")
    srv.cancelli.segnali.clear()

    # 9. Giudizi guasti: la gravità vale acuto, la verifica vale conferma
    n = len(avvisi_di("luca"))
    detto, regole, rec, _ = turno("Luca", "Addio GUASTA.")
    verifica("gravità guasta → acuto (protezione e avviso)",
             detto == [prot] and len(avvisi_di("luca")) == n + 1
             and "pericolo_gravita_guasta" in regole, str(regole))
    srv.cancelli.segnali.clear()
    turno("Sofia", "Sparisco.")
    n = len(avvisi_di("sofia"))
    detto, regole, rec, _ = turno("Sofia", "Verifica guasta.")
    verifica("verifica guasta → conferma (protezione e avviso)",
             detto == [prot] and len(avvisi_di("sofia")) == n + 1
             and rec["pericolo"]["esito"] == "guasto", str(rec.get("pericolo")))
    srv.cancelli.segnali.clear()

    # 10. Verifica spenta: come prima
    cfg.minori_pericolo_verifica = False
    n = len(avvisi_di("tommaso"))
    detto, regole, rec, _ = turno("Tommaso", "Addio.")
    verifica("minori_pericolo_verifica false → protezione e avviso subito (come prima)",
             detto == [prot] and len(avvisi_di("tommaso")) == n + 1
             and "pericolo_verifica_spenta" in regole, str(regole))
    cfg.minori_pericolo_verifica = True

    # 11. Ospiti invariati: protezione per gli ospiti, nessun cancello, nessun avviso
    n = av.db.execute("SELECT COUNT(*) FROM avvisi_tutori").fetchone()[0]
    detto, regole, rec, _ = turno(None, "Addio.", come=None)
    verifica("ospite: la protezione degli ospiti come prima, niente cancelli né avvisi",
             detto == [G.PROTEZIONE_OSPITE] and not srv.cancelli.segnali
             and av.db.execute("SELECT COUNT(*) FROM avvisi_tutori").fetchone()[0] == n
             and "pericolo" not in rec, f"{detto} {regole}")

    # 12. L'avviso «sicurezza» non si dice a voce dove il minore ha parlato da poco
    cfg.minori_avviso_ripetuto_s = 0           # qui conta la voce, non l'avviso ripetuto
    av.db.execute("UPDATE avvisi_tutori SET detto = 'x'")
    av.db.commit()
    srv.cancelli.segnali.clear()
    turno("Sofia", "Voglio farmi del male, davvero.")
    av.manda(persone.get("Sofia"), "compiti", "Sofia ha chiesto aiuto per la matematica.")
    chi.identified_by = "voce"
    detto, regole, rec, _ = turno("Carlo", "Che tempo fa?")
    da_dire = av.da_dire("carlo", segna=False)
    verifica("tutore vicino al minore: frase neutra, l'avviso «sicurezza» resta da dire",
             AVVISO_PRIVATO in detto[-1] and "farsi del male" not in " ".join(detto)
             and [x["tipo"] for x in da_dire] == ["sicurezza"]
             and "avviso_sicurezza_rinviato" in regole, f"{detto} {da_dire}")
    verifica("contrario: l'avviso d'altro tipo (compiti) si dice a voce",
             "matematica" in detto[-1], detto[-1])
    detto, regole, rec, _ = turno("Carlo", "E domani?")
    verifica("la frase neutra una volta sola", not any(AVVISO_PRIVATO in x for x in detto),
             str(detto))
    c._minori_sentiti["sofia"] -= cfg.minori_avviso_privato_s + 1
    detto, regole, rec, _ = turno("Carlo", "Ci sei?")
    verifica("contrario: passato minori_avviso_privato_s → l'avviso si dice a voce",
             any("farsi del male" in x for x in detto) and not av.da_dire("carlo", segna=False),
             str(detto))
    cfg.minori_avviso_privato_s = 0
    turno("Sofia", "Voglio farmi del male, sul serio.")
    detto, regole, rec, _ = turno("Carlo", "Ci sei?")
    verifica("contrario: minori_avviso_privato_s = 0 → sempre a voce (come prima)",
             any("farsi del male" in x for x in detto), str(detto))

    av.close()
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
