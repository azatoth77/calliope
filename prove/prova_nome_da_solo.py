"""
Il nome da solo e la modalità Star Trek in uso (06/10/2026, caso vero della DGX).

    python prove/prova_nome_da_solo.py

Sul satellite «studio», in modalità startrek: «Computer» detto da solo arrivava al server (la
wake word acustica del satellite era scattata) ma Whisper dava un testo vuoto (esito «vuoto»:
niente suono, niente ascolto) oppure «Come più tardi.» (0,76 s di voce), che andava al modello
come domanda: `conversazione_cerca({})` senza argomenti, «Fammi ricordare.» e la risposta «…».
Dopo «Calliope» da solo il bip di fine (frase presa) faceva credere l'ascolto chiuso.

Qui, a secco, un `Ciclo` con un satellite finto (`started_at`, `woke`, `wake_score` come
`SatListener`), Whisper, voce e Brain finti:
- frase vuota con lo scatto sicuro a Calliope addormentata → nome da solo (saluto, finestra);
  storpiato e breve («Come più tardi.», 0,76 s) → nome da solo, non al modello;
- con i suoni (startrek): di nuovo il suono d'inizio, finestra aperta, suono di fine se nessuno
  parla; nessun suono di fine se una frase arriva;
- contrari: scatto debole con il testo vuoto (scartato), frase vuota nella finestra (vuoto),
  frase lunga senza il nome con lo scatto sicuro (va al modello come prima), il nome trascritto
  con la domanda (vale ciò che segue);
- `Speaker.suono` manda il PCM anche con l'uscita del satellite;
- `ToolRegistry`: una chiamata senza nessun argomento obbligatorio non parte (niente frase
  d'attesa in Brain); con qualche argomento passa com'è;
- Brain: risposta fatta solo di punteggiatura («…») non si dice: seconda passata, poi la frase
  di ripiego; contrario: una risposta vera dopo lo stesso tool.
Niente audio, modelli né rete: ~2 s.
"""
import os
import queue
import sys
import threading
import time
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from calliope import corsie  # noqa: E402
from calliope.ciclo import Ciclo, Servizi, solo_nome_acustico  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.cortesia import Cortesia  # noqa: E402
from calliope.suoni import FINE, INIZIO  # noqa: E402

errori = 0


def verifica(nome, cond, extra=""):
    global errori
    if not cond:
        errori += 1
    print(("ok  " if cond else "ERR ") + nome + (f"  ({extra})" if extra else ""), flush=True)


class SatelliteFinto:
    """Il contratto di SatListener: la frase arriva intera, con woke e wake_score del
    satellite. `frasi`: (secondi di voce, woke, wake_score)."""
    remoto = True

    def __init__(self):
        self.frasi = []
        self.started_at = self.ended_at = 0.0
        self.woke, self.wake_score = False, 0.0
        self.on_speech_start = self.on_speech_end = None
        self.ascolti = []          # awake_until passato a ogni listen

    def listen(self, wake, awake_until, seed=None, wakeup=None):
        voce_s, woke, score = self.frasi.pop(0)
        self.ascolti.append(awake_until)
        self.started_at = self.ended_at = time.monotonic()
        self.woke, self.wake_score = woke, score
        # pre-roll e silenzio di chiusura come quelli veri (Config: 300 + 700 ms)
        return np.zeros(int((voce_s + 1.0) * 16000), dtype=np.float32)


class Whisper:
    def __init__(self):
        self.frasi = []

    def transcribe(self, audio):
        return self.frasi.pop(0)


class Voce:
    interrupted, muto, _current_voice_path, on_parla = False, False, "", None

    def __init__(self):
        self.detto, self.suoni = [], []

    def say(self, t):
        self.detto.append(t)
    say_cached = say

    def suono(self, suoni, tipo):
        self.suoni.append(tipo)

    def wait(self, *a):
        return True

    def start_turn(self):
        pass

    def chime(self, *a):
        pass
    suono_ascolto = prepare = change_voice = chime


class Suoni:
    attivi = True


class ChiParla:
    is_enrolling, enrolling_name, enroll_expired = False, None, False
    identified_by, from_session, conferma_breve, sfida_superata = None, False, False, False
    current_speaker = None

    @property
    def current_level(self):
        return "ospite"

    def aggiorna_conversazione(self, *a):
        pass


class Persone:
    users: dict = {}
    illeggibile = False

    def get(self, nome):
        return None


class Cervello:
    last_tools, last_private, on_tool_start, conv, turn_number = [], False, None, None, 0
    uso_precedente = last_context = last_compressione = last_lettura_s = None

    def __init__(self):
        self.richieste = []

    def stream_reply(self, text, level, context=None, **k):
        self.richieste.append(text)
        yield f"Risposta a «{text}»."

    def end_conversation(self, motivo="fine"):
        pass

    def has_pending(self):
        return False

    def ultima_domanda(self):
        return False

    def record_courtesy(self, *a):
        pass

    def strip_tool_mentions(self, s):
        return s

    def speak_tool_names(self, s):
        return s

    def mentions_tool(self, s):
        return False

    def redact(self, s):
        return s

    def rules_fired(self):
        return []

    def vede_immagini(self):
        return False

    def record_stop(self, *a):
        pass


def nuovo_ciclo(suoni_accesi: bool):
    cfg = Config()
    cfg.speaker_id_enabled = False
    cfg.barge_in_enabled = False
    cfg.debug_audio_dir = None
    cfg.uscita_controllo = False
    cfg.followup_s = 0.4
    if suoni_accesi:
        cfg.suoni_ascolto = True
    turni = []
    sat, stt, voce, cervello = SatelliteFinto(), Whisper(), Voce(), Cervello()
    instr = types.SimpleNamespace(dopo_turno=lambda x: x, inizio_voce=lambda: None,
                                  persona=lambda *a: None, origine=lambda: {},
                                  annuncia_verso=lambda *a, **k: None,
                                  risposta_scritta=lambda *a: None)
    srv = Servizi(cfg, registry=Persone(), stt=stt, instradamento=instr, cortesia=Cortesia(),
                  turns=types.SimpleNamespace(write=lambda r: turni.append(dict(r))),
                  attiva_minori=lambda: False, biblioteca=object(), enroll_pending=False)
    srv.wake = object()                       # la wake word acustica (sul satellite)
    srv.suoni = Suoni() if suoni_accesi else None
    annunci = types.SimpleNamespace(agenda=queue.Queue(), documenti=None, installazioni=None,
                                    lavori=None, estensioni=None)
    c = Ciclo(srv, corsie.Corsia("studio"), sat, voce, ChiParla(), cervello,
              types.SimpleNamespace(), annunci, None, threading.Event())

    def giro(testo, voce_s=0.7, woke=True, score=1.0):
        stt.frasi.append(testo)
        sat.frasi.append((voce_s, woke, score))
        n, m = len(voce.detto), len(cervello.richieste)
        c.giro()
        c._inizio_giro()                      # scrive il turno nel registro
        return voce.detto[n:], cervello.richieste[m:], turni[-1]
    return c, giro, voce, cervello, sat


def prova_regola():
    cfg = Config()
    verifica("regola: testo vuoto → nome da solo", solo_nome_acustico("", 2.0, cfg))
    verifica("regola: solo punteggiatura → nome da solo", solo_nome_acustico(" … ", 2.0, cfg))
    verifica("regola: «Come più tardi.» in 0,76 s → nome da solo",
             solo_nome_acustico("Come più tardi.", 0.76, cfg))
    verifica("contrario: «Accendi la luce in taverna» in 1,6 s → non è il nome",
             not solo_nome_acustico("Accendi la luce in taverna", 1.6, cfg))
    verifica("valore predefinito wake_solo_nome_s 0,9", cfg.wake_solo_nome_s == 0.9)


def prova_senza_suoni():
    c, giro, voce, cervello, sat = nuovo_ciclo(False)
    detto, chieste, rec = giro("", 0.7)
    verifica("vuoto con lo scatto sicuro, addormentata: saluto, non «vuoto»",
             rec["esito"] == "saluto" and detto == ["Sì?"] and not chieste, f"{rec} {detto}")
    verifica("regola nome_da_solo_acustico nel registro",
             "nome_da_solo_acustico" in (rec.get("regole") or []), rec.get("regole"))
    verifica("risveglio nel registro anche col testo vuoto", rec.get("risveglio") == 1.0,
             rec.get("risveglio"))
    verifica("finestra aperta dopo il nome", c.awake_until > time.monotonic())
    detto, chieste, rec = giro("che ore sono?", 0.9, woke=False, score=0.0)
    verifica("nella finestra la domanda va al modello senza il nome",
             chieste == ["che ore sono?"] and rec["esito"] == "risposta", f"{chieste} {rec}")
    time.sleep(0.45)                          # la finestra si chiude
    detto, chieste, rec = giro("Come più tardi.", 0.76)
    verifica("«Come più tardi.» (0,76 s) addormentata: nome da solo, non al modello",
             rec["esito"] == "saluto" and not chieste, f"{rec} {chieste}")
    time.sleep(0.45)
    detto, chieste, rec = giro("", 0.7, score=0.6)
    verifica("contrario: testo vuoto con lo scatto debole: scartato in silenzio",
             rec["esito"] == "scartato" and not detto and not chieste, f"{rec}")
    detto, chieste, rec = giro("Accendi la luce in taverna", 1.6)
    verifica("contrario: frase lunga senza il nome, scatto sicuro: al modello come prima",
             chieste == ["Accendi la luce in taverna"], f"{chieste} {rec}")
    time.sleep(0.45)
    detto, chieste, rec = giro("Calliope, che ore sono?", 1.4)
    verifica("contrario: il nome con la domanda: vale ciò che segue",
             [x.rstrip("?") for x in chieste] == ["che ore sono"], f"{chieste}")
    detto, chieste, rec = giro("", 0.5, woke=False, score=0.0)
    verifica("contrario: frase vuota nella finestra (senza scatto): «vuoto»",
             rec["esito"] == "vuoto" and not detto, f"{rec}")


def prova_con_suoni():
    c, giro, voce, cervello, sat = nuovo_ciclo(True)
    detto, chieste, rec = giro("", 0.7)
    verifica("startrek, «Computer» da solo: suono d'inizio, niente parole",
             voce.suoni == [INIZIO] and not detto and not chieste and rec["esito"] == "saluto",
             f"{voce.suoni} {detto} {rec}")
    verifica("regola nome_da_solo_suono", "nome_da_solo_suono" in (rec.get("regole") or []),
             rec.get("regole"))
    time.sleep(0.6)
    verifica("nessuno parla: alla chiusura della finestra il suono di fine",
             voce.suoni == [INIZIO, FINE], voce.suoni)
    # Di nuovo il nome, poi il comando dentro la finestra: nessun suono di fine dal server
    # (quello della frase presa lo suona il satellite)
    detto, chieste, rec = giro("Computer.", 0.6)
    detto, chieste, rec = giro("che ore sono?", 0.9, woke=False, score=0.0)
    time.sleep(0.6)
    verifica("il comando arriva nella finestra: risposta e niente suono di fine dal server",
             chieste == ["che ore sono?"] and voce.suoni == [INIZIO, FINE, INIZIO],
             f"{chieste} {voce.suoni}")
    verifica("dopo il nome la voce ascolta con la finestra aperta (sveglia_per_s > 0)",
             sat.ascolti[-1] > time.monotonic() - 1.0)


def prova_speaker_suono():
    from calliope.tts import Speaker
    sp = Speaker.__new__(Speaker)
    sp.muto, sp.out, sp._rate, sp.audio_q = False, None, 22050, queue.Queue()
    sp.remota = object()                      # l'uscita del satellite

    class S:
        def pcm(self, tipo, rate):
            return f"{tipo}@{rate}".encode()
    sp.suono(S(), INIZIO)
    verifica("Speaker.suono con il satellite: il PCM va in coda come una frase senza testo",
             sp.audio_q.get_nowait() == ("", b"inizio@22050"))
    sp.suono(None, INIZIO)
    verifica("Speaker.suono senza suoni: niente", sp.audio_q.empty())


def prova_argomenti_mancanti():
    import dataclasses
    from prove.prova_politica import prepara, turno, chiama, testo
    b, eseguiti, _ = prepara()
    reg = b.tools
    chiamato = []
    from calliope.tools.conversazioni import conversazioni_specs
    spec = next(x for x in conversazioni_specs() if x.name == "conversazione_cerca")
    reg.register(dataclasses.replace(spec, func=lambda ctx, **a: chiamato.append(a) or {
        "ok": True, "risultati": []}))
    verifica("schema: conversazione_cerca vuole «domanda»",
             spec.parameters.get("required") == ["domanda"])
    verifica("mancanti: chiamata vuota", reg.mancanti("conversazione_cerca", {}) == ["domanda"])
    verifica("mancanti: argomento vuoto", reg.mancanti("conversazione_cerca", {"domanda": " "})
             == ["domanda"])
    verifica("contrario: con un argomento qualsiasi passa (completano i tool)",
             reg.mancanti("delega_lavoro", {"proposta": "L1"}) == [])
    attese = []
    b.on_tool_start = attese.append
    r = turno(b, "di cosa abbiamo parlato ieri?", chiama("conversazione_cerca", {}),
              testo("Non trovo niente."))
    verifica("conversazione_cerca({}): niente frase d'attesa, niente ricerca, errore al modello",
             not attese and not chiamato and "tool_argomenti_mancanti" in b.rules_fired(),
             f"{attese} {chiamato} {b.rules_fired()}")
    verifica("…e la risposta del modello dopo l'errore si dice", r == "Non trovo niente.", r)
    r = turno(b, "di cosa abbiamo parlato ieri?",
              chiama("conversazione_cerca", {"domanda": "ieri"}), testo("Del preventivo."))
    verifica("contrario: con la domanda la frase d'attesa e la ricerca partono",
             attese and chiamato == [{"domanda": "ieri"}] and r == "Del preventivo.",
             f"{attese} {chiamato} {r}")


def prova_punteggiatura():
    from prove.prova_politica import prepara, turno, chiama, testo
    b, _, _ = prepara()
    r = turno(b, "cosa ti avevo detto?", chiama("ora_attuale", {}), testo("…"),
              testo("Erano le dieci."))
    verifica("«…» dopo un tool: seconda passata e la risposta vera",
             "Erano le dieci." in r and "risposta_solo_punteggiatura" in b.rules_fired(),
             f"{r!r} {b.rules_fired()}")
    r = turno(b, "e allora?", testo("…"), testo("."))
    verifica("di nuovo solo punteggiatura: la frase di ripiego, non il silenzio",
             "puoi ripetere" in r, repr(r))
    r = turno(b, "che ore sono?", chiama("ora_attuale", {}), testo("Sono le dieci."))
    verifica("contrario: una risposta vera non cambia",
             r == "Sono le dieci." and "risposta_solo_punteggiatura" not in b.rules_fired(),
             repr(r))
    from calliope.ciclo import Ciclo as C
    finto = types.SimpleNamespace(s=types.SimpleNamespace(cfg=Config()), rule=lambda n: None,
                                  brain=types.SimpleNamespace(
                                      strip_tool_mentions=lambda s: s,
                                      mentions_tool=lambda s: False, last_tools=[]))
    t = types.SimpleNamespace(context=None)
    verifica("ciclo: «…» non va alla voce", C._frase_da_dire(finto, t, "…") == "")
    verifica("ciclo: contrario, «Sì.» va alla voce", C._frase_da_dire(finto, t, "Sì.") == "Sì.")


def main():
    prova_regola()
    prova_senza_suoni()
    prova_con_suoni()
    prova_speaker_suono()
    prova_argomenti_mancanti()
    prova_punteggiatura()
    print(f"\n{errori} errori" if errori else "\nTutto a posto.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
