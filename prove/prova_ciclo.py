"""
Il ciclo della voce a secco (06/10/2026, P8 dell'analisi complessiva: calliope/ciclo.py).

    python prove/prova_ciclo.py

Un `Ciclo` con ascolto, Whisper, voce, chi parla e Brain finti, giro per giro, sulle fasi che
le prove con Calliope vera non toccano: primo avvio (solo il nome → registrazione di
«Primo»), frase di registrazione senza il nome (promemoria una volta sola), registrazione
finita e nome vero detto («Mi chiamo Dario»), domanda nella finestra di ascolto,
«approfondisci» (contesto della biblioteca), ricerca promessa e fatta, «ricominciamo»,
cortesia, frase non rivolta a Calliope (non resta nel registro), «esci», «spegniti»;
«esci» in una corsia di satellite: si addormenta e il ciclo continua (Q10).
Niente audio, modelli né rete: ~1 s.
"""
import os
import queue
import sys
import threading
import time
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from calliope import ciclo as ciclo_mod, corsie  # noqa: E402
from calliope.ciclo import Ciclo, Servizi  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.cortesia import Cortesia  # noqa: E402

errori = 0


def verifica(nome, cond, extra=""):
    global errori
    if not cond:
        errori += 1
    print(("ok  " if cond else "ERR ") + nome + (f"  ({extra})" if extra else ""), flush=True)


class Ascolto:
    started_at, wake_score, ended_at = 0.0, 0.0, 0.0
    on_speech_start = on_speech_end = None

    def listen(self, wake, awake_until, seed=None, wakeup=None):
        self.started_at = self.ended_at = time.monotonic()
        return np.zeros(16000, dtype=np.float32)


class Whisper:
    ATTESA = "Un attimo."

    def __init__(self):
        self.frasi = []

    def transcribe(self, audio):
        return self.frasi.pop(0)


class Voce:
    interrupted, muto, _current_voice_path, on_parla = False, False, "", None

    def __init__(self):
        self.detto, self.played = [], []

    def say(self, t):
        self.detto.append(t)
    say_cached = say

    def wait(self, *a):
        return True

    def start_turn(self):
        pass

    def chime(self, *a):
        pass
    suono_ascolto = prepare = change_voice = chime


class ChiParla:
    """Il minimo di SpeakerContext che usa il ciclo."""

    def __init__(self):
        self.is_enrolling, self.enrolling_name, self.enroll_expired = False, None, False
        self.current_speaker, self.identified_by, self.from_session = None, None, False
        self.conferma_breve = self.sfida_superata = False
        self.enroll_prompt, self.enroll_remaining, self.enroll_needed = "Dimmi una frase.", 2, 3
        self.esiti = ["prima", "ancora", "fatto"]   # la prima è quella del nome

    @property
    def current_level(self):
        return "amministra" if self.current_speaker else "ospite"

    def start_enroll(self, nome, admin=False):
        self.is_enrolling, self.enrolling_name = True, nome

    def enroll_sample(self, audio, sr, detect_gender=False, voiced_s=0.0):
        esito = self.esiti.pop(0)
        if esito == "fatto":
            self.is_enrolling = False
        return esito

    def stop_enroll(self):
        self.is_enrolling, self.enrolling_name = False, None

    def aggiorna_conversazione(self, *a):
        pass


class Persone:
    users: dict = {}
    illeggibile = False

    def __init__(self):
        self.rinominati = []

    def get(self, nome):
        return types.SimpleNamespace(name=nome, id=nome.lower(), preferred_voice=None,
                                     preferred_tone=None) if nome else None

    def rename(self, vecchio, nuovo):
        self.rinominati.append((vecchio, nuovo))
        return self.get(nuovo)


class Cervello:
    last_tools, last_private, on_tool_start, conv, turn_number = [], False, None, None, 0
    uso_precedente = last_context = last_compressione = last_lettura_s = None
    ricerca = None                       # brain.ricerca_recente (09/10)

    def __init__(self):
        self.richieste, self.fine, self.risposte = [], [], []

    def stream_reply(self, text, level, context=None, **k):
        self.richieste.append((text, context))
        yield self.risposte.pop(0) if self.risposte else f"Risposta a «{text}»."

    def stream_continuation(self, level, context=None):
        self.richieste.append(("(continuazione)", context))
        yield "Il Po è lungo 652 km."

    def ricerca_recente(self):
        return self.ricerca

    def end_conversation(self, motivo="fine"):
        self.fine.append(motivo)

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


def main():
    cfg = Config()
    cfg.speaker_id_enabled = False
    cfg.barge_in_enabled = False
    cfg.debug_audio_dir = None
    cfg.uscita_controllo = False
    turni = []
    stt, voce, chi, cervello, persone = Whisper(), Voce(), ChiParla(), Cervello(), Persone()
    instr = types.SimpleNamespace(dopo_turno=lambda x: x, inizio_voce=lambda: None,
                                  persona=lambda *a: None, origine=lambda: {},
                                  annuncia_verso=lambda *a, **k: None,
                                  risposta_scritta=lambda *a: None)
    srv = Servizi(cfg, registry=persone, stt=stt, instradamento=instr, cortesia=Cortesia(),
                  turns=types.SimpleNamespace(write=lambda r: turni.append(dict(r))),
                  attiva_minori=lambda: False, biblioteca=object(), enroll_pending=True)
    annunci = types.SimpleNamespace(agenda=queue.Queue(), documenti=None, installazioni=None,
                                    lavori=None, estensioni=None)
    c = Ciclo(srv, corsie.Corsia("locale"), Ascolto(), voce, chi, cervello,
              types.SimpleNamespace(), annunci, None, threading.Event())
    ciclo_mod.biblioteca_contesto = lambda ctx, domanda: f"CONTESTO di «{domanda}»"

    def giro(frase, risposta=None):
        stt.frasi.append(frase)
        if risposta is not None:
            cervello.risposte.append(risposta)
        n = len(voce.detto)
        esito = c.giro()
        return esito, voce.detto[n:]

    _, detto = giro("Calliope.")
    verifica("primo avvio: solo il nome → registrazione di «Primo»",
             detto and detto[0].startswith("Ah, sei il mio Primo!") and chi.is_enrolling
             and not srv.enroll_pending, str(detto))
    _, detto = giro("E adesso le previsioni del tempo per domani.")
    _, detto2 = giro("Anche domani sole su tutta Italia.")
    verifica("registrazione: frase senza il nome non contata, promemoria una volta sola",
             detto == ["Comincia la frase con il mio nome, così so che parli a me."]
             and detto2 == [] and chi.esiti == ["ancora", "fatto"]
             and "arruolamento_senza_nome" in (c.rec or {}).get("regole", []), str(detto))
    _, detto = giro("Calliope, oggi sono andato al mare.")
    verifica("registrazione: una frase con il nome, ne manca ancora",
             detto and detto[0].startswith("Grazie. Ancora 2"), str(detto))
    _, detto = giro("Calliope, mi piace molto la pizza margherita.")
    verifica("registrazione finita: «Vuoi dirmi il tuo nome?»",
             detto == ["Registrato Primo. Ora ti riconosco.", "Vuoi dirmi il tuo nome?"]
             and c.pending_real_name == "Primo", str(detto))
    _, detto = giro("Mi chiamo Dario.")
    verifica("nome vero: «Mi chiamo Dario» → Dario",
             detto == ["Ok, ti chiamerò Dario."] and persone.rinominati == [("Primo", "Dario")]
             and c.pending_real_name is None and "nome_detto" in c.rec.get("regole", []),
             str(detto))
    _, detto = giro("Che ore sono?")
    verifica("nella finestra di ascolto la domanda va al modello senza il nome",
             detto == ["Risposta a «Che ore sono?»."] and c.last_question == "Che ore sono?",
             str(detto))
    _, detto = giro("Approfondisci.")
    verifica("«approfondisci»: la domanda di prima cercata nella biblioteca",
             detto[0] == "Controllo nella biblioteca."
             and cervello.richieste[-1] == ("Approfondisci.", "CONTESTO di «Che ore sono?»")
             and c.last_question == "Che ore sono?", str(detto))
    # Dopo una ricerca nei turni prima (09/10, caso vero della DGX): decide il modello, con
    # l'ultima ricerca nei suoi dati del turno; niente biblioteca con la domanda di prima
    cervello.ricerca = {"tool": "web_cerca", "domanda": "ultime notizie"}
    _, detto = giro("Approfondisci.")
    cervello.ricerca = None
    verifica("«approfondisci» dopo una ricerca: al modello, senza la biblioteca",
             cervello.richieste[-1] == ("Approfondisci.", None)
             and "approfondisci_al_modello" in c.rec.get("regole", [])
             and "approfondisci" not in c.rec.get("regole", []), str(detto))
    _, detto = giro("Quanto è lungo il Po?", "Devo fare una ricerca per risponderti bene.")
    verifica("ricerca promessa e fatta subito",
             detto == ["Devo fare una ricerca per risponderti bene.",
                       "Controllo nella biblioteca.", "Il Po è lungo 652 km."]
             and c.rec.get("ricerca_promessa") and "ricerca_promessa" in c.rec.get("regole", [])
             and cervello.richieste[-1] == ("(continuazione)",
                                            "CONTESTO di «Quanto è lungo il Po?»"), str(detto))
    _, detto = giro("Ricominciamo.")
    verifica("«ricominciamo»: conversazione nuova, resta in ascolto",
             detto == ["Va bene, ricominciamo da capo."] and cervello.fine == ["nuova"]
             and c.awake_until > time.monotonic(), str(detto))
    _, detto = giro("Grazie.")
    verifica("cortesia: una frase breve senza il modello, finestra chiusa",
             len(detto) == 1 and c.rec["esito"] == "cortesia" and c.awake_until == 0.0,
             str(detto))
    _, detto = giro("Che tempo fa domani?")
    verifica("addormentata: una frase senza il nome si ignora e non resta nel registro",
             detto == [] and c.rec["esito"] == "ignorato" and c.rec["testo"] is None,
             str(c.rec))
    _, detto = giro("Calliope, esci.")
    verifica("«esci»: «A presto!» e la conversazione si chiude",
             detto == ["A presto!"] and cervello.fine == ["nuova", "fine"]
             and c.awake_until == 0.0, str(detto))
    esito, detto = giro("Calliope, spegniti.")
    verifica("«spegniti»: «Mi spengo» e il giro restituisce «esci»",
             esito == "esci" and detto == ["Mi spengo. A presto!"]
             and turni[-1]["esito"] == "uscita", f"{esito} {detto}")
    verifica("registro dei turni: un turno per giro (scritto in cima al giro dopo)",
             len(turni) >= 12, str(len(turni)))

    # Q10 (06/10): «esci» da un giro in una corsia di satellite non chiude il thread (il
    # satellite resterebbe sordo, ancora registrato nello smistatore): si addormenta e
    # continua. La corsia locale invece esce come prima
    def esegui_con(corsia, esiti):
        k = Ciclo(srv, corsia, Ascolto(), Voce(), chi, Cervello(), types.SimpleNamespace(),
                  annunci, None, threading.Event())
        fine, giri = threading.Event(), []

        def giro_finto():
            giri.append(1)
            e = esiti[len(giri) - 1] if len(giri) <= len(esiti) else None
            if len(giri) >= len(esiti):
                fine.set()
            return e
        k.giro = giro_finto
        k.awake_until, k.rec = time.monotonic() + 30, {"esito": "uscita"}
        n = len(turni)
        th = threading.Thread(target=k.esegui, args=(fine,), daemon=True)
        th.start()
        th.join(5)
        return k, giri, not th.is_alive(), len(turni) - n
    k, giri, finito, scritti = esegui_con(corsie.Corsia("sat:7", satellite_id=7),
                                          ["esci", None, None])
    verifica("«esci» in una corsia di satellite: si addormenta e continua",
             finito and len(giri) == 3 and k.awake_until == 0.0 and k.brain.fine == ["fine"]
             and k.rec is None and scritti == 0, f"{len(giri)} giri, {k.brain.fine}")
    k, giri, finito, _ = esegui_con(corsie.Corsia("locale"), ["esci", None, None])
    verifica("contrario: nella corsia locale «esci» chiude il ciclo (come prima)",
             finito and len(giri) == 1, f"{len(giri)} giri")
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
