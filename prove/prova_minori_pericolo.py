"""
Minore in pericolo con la frase spezzata (06/10/2026, prova e2e sulla DGX, giro 0944).

    python prove/prova_minori_pericolo.py

Sofia: «un signore al parco mi ha detto di andare a casa sua» | «e di non dirlo alla mamma».
Il secondo pezzo, detto mentre Calliope rispondeva, la interrompeva con la sola voce (barge-in
di livello B) e l'avviso «sicurezza» ai tutori partiva due volte. Un `Ciclo` con voce,
ascolto, guardiano e Brain finti (le fasi `_rispondi`, `_registra_risposta`,
`_dopo_la_risposta`) e gli avvisi veri su un database temporaneo:

- il pezzo detto interrompendo si giudica unito al pezzo di prima (`guardia_pezzi_uniti`);
  contrari: un'altra persona, una frase non interrotta, oltre `UNIONE_PEZZI_S`;
- la protezione non si interrompe con la sola voce (`known_voice`), solo con il nome; se il
  nome la interrompe, si ripete per intero al turno dopo della stessa persona
  (`protezione_interrotta`, `protezione_ripetuta`); contrari: un'altra persona nel mezzo, la
  protezione già ripetuta;
- lo stesso avviso (stesso minore, stesso argomento) non si ripete entro
  `minori_avviso_ripetuto_s` (`avviso_pericolo_ripetuto`); contrari: argomento diverso, altro
  minore, finestra passata, finestra a 0.
Niente audio, modelli né rete: ~2 s.
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

import numpy as np  # noqa: E402

from calliope import corsie, guardiano as G, minori  # noqa: E402
from calliope.ciclo import Ciclo, Servizi, Turno  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.cortesia import Cortesia  # noqa: E402

errori = 0


def verifica(nome, cond, extra=""):
    global errori
    if not cond:
        errori += 1
    print(("ok  " if cond else "ERR ") + nome + (f"  ({extra})" if extra else ""), flush=True)


class Voce:
    """La voce finta: una frase è «detta per intero» (played) se nessuno l'ha interrotta prima
    della fine del turno; `durante` ricorda se la protezione era segnata come in corso."""
    muto, _current_voice_path, on_parla = False, "", None

    def __init__(self):
        self.detto, self.played, self._in_coda = [], [], []
        self.interrupted, self.ciclo, self.durante, self.ultimo = False, None, [], []

    def say(self, t):
        self.detto.append(t)
        self.durante.append((t, bool(getattr(self.ciclo, "protezione_in_corso", False))))
        self._in_coda.append(t)
    say_cached = say

    def saying_name(self):
        return False

    def wait(self, *a):
        time.sleep(0.15)                 # il tempo per l'ascolto del nome di agire
        if not self.interrupted:
            self.played.extend(self._in_coda)
        self._in_coda = []
        return True

    def interrupt(self):
        self.interrupted = True

    def start_turn(self):
        self.ultimo = list(self.played)          # le frasi dette per intero nel turno finito
        self.played, self._in_coda, self.interrupted = [], [], False

    def chime(self, *a):
        pass
    suono_ascolto = prepare = change_voice = chime


class Ascolto:
    """Barge-in finto. modo None: nessuno parla; "voce": chi parla interrompe con la sola
    voce (livello B: decide `voice_ok`); "nome": interrompe con il nome."""
    started_at = ended_at = wake_score = 0.0
    on_speech_start = on_speech_end = None

    def __init__(self, voce):
        self.voce, self.modo, self.voice_ok = voce, None, []

    def watch_for_name(self, wake, stop, saying_name, voice_ok=None):
        if self.modo is None:
            stop.wait()
            return None
        while not self.voce.detto[self.inizio:] and not stop.is_set():
            time.sleep(0.005)
        if stop.is_set():
            return None
        if self.modo == "voce":
            ok = bool(voice_ok(np.zeros(16000, dtype=np.float32))) if voice_ok else False
            self.voice_ok.append(ok)
            if not ok:
                stop.wait()
                return None
        return [np.zeros(1600, dtype=np.float32)]      # il seme: l'audio con il nome


class Guardia:
    """Il guardiano finto: «pericolo» sulla domanda se c'è un signore che chiede di non dirlo
    alla mamma (le due metà insieme) o se parla di farsi del male."""
    timeout_s = 1.0

    def __init__(self, cfg):
        self.cfg, self.domande = cfg, []

    def condivide_voce(self):
        return False

    def in_parallelo(self, domanda, frase, categorie):
        f = concurrent.futures.Future()
        d = domanda.lower()
        if frase is None:
            self.domande.append(domanda)
        if frase is None and "signore" in d and "non dirlo" in d:
            f.set_result(G.Giudizio(G.PERICOLO, ("abuso",)))
        elif frase is None and "farmi del male" in d:
            f.set_result(G.Giudizio(G.PERICOLO, ("autolesionismo",)))
        else:
            f.set_result(G.Giudizio(G.OK))
        return f


class Persone:
    def __init__(self):
        nascita = (datetime.date.today() - datetime.timedelta(days=9 * 366)).isoformat()
        p = types.SimpleNamespace
        self.users = {
            "Carlo": p(name="Carlo", id="carlo", admin=True, preferred_voice=None,
                       preferred_tone=None),
            "Sofia": p(name="Sofia", id="sofia", nascita=nascita, tutori=["carlo"],
                       preferred_voice=None, preferred_tone=None),
            "Luca": p(name="Luca", id="luca", nascita=nascita, tutori=["carlo"],
                      preferred_voice=None, preferred_tone=None)}

    def get(self, nome):
        return self.users.get(nome)

    def embed(self, audio, sr):
        return None

    def best_match(self, emb=None):
        return "Sofia", 0.70


class ChiParla:
    is_enrolling, enrolling_name, enroll_expired = False, None, False
    identified_by, from_session = None, False

    def __init__(self):
        self.current_speaker = None

    @property
    def current_level(self):
        return "familiare" if self.current_speaker else "ospite"


class Cervello:
    last_tools, last_private, on_tool_start, conv, turn_number = [], False, None, None, 0
    uso_precedente = last_context = last_compressione = last_lettura_s = None
    trattieni_schede = schede_attesa_ms = None

    def __init__(self):
        self.richieste, self.history = [], []

    def stream_reply(self, text, level, context=None, **k):
        self.richieste.append(text)
        yield f"Risposta a «{text}»."

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
    cartella = tempfile.mkdtemp(prefix="calliope-pericolo-")
    cfg.memory_db = os.path.join(cartella, "memoria.db")
    persone = Persone()
    righe = []
    minori.prepara(cfg, registry=persone, log=lambda m: righe.append(m))
    av = minori.avvisi()
    voce, cervello, chi = Voce(), Cervello(), ChiParla()
    ascolto = Ascolto(voce)
    instr = types.SimpleNamespace(dopo_turno=lambda x: x, inizio_voce=lambda: None,
                                  persona=lambda *a: None, origine=lambda: {},
                                  annuncia_verso=lambda *a, **k: None,
                                  risposta_scritta=lambda *a: None)
    guardia = Guardia(cfg)
    srv = Servizi(cfg, registry=persone, instradamento=instr, cortesia=Cortesia(),
                  turns=types.SimpleNamespace(write=lambda r: None),
                  attiva_minori=lambda: True, guardiano=guardia, wake=object(),
                  barge_in=True, barge_voice=True)
    srv.controllo_impronte[0] = time.monotonic()      # niente promemoria delle impronte
    annunci = types.SimpleNamespace(agenda=queue.Queue(), documenti=None, installazioni=None,
                                    lavori=None, estensioni=None)
    c = Ciclo(srv, corsie.Corsia("locale"), ascolto, voce, chi, cervello,
              types.SimpleNamespace(), annunci, None, threading.Event())
    voce.ciclo = c

    def turno(nome, testo, barged=False, modo=None):
        chi.current_speaker = nome
        ascolto.modo, ascolto.inizio = modo, len(voce.detto)
        t = Turno(text=testo, speaker_name=nome, barged=barged, prof_turno=persone.get(nome))
        c.rec = {}
        n = len(voce.detto)
        c._rispondi(t)
        c._registra_risposta(t)
        c._dopo_la_risposta(t)
        return t, voce.detto[n:], c.rec.get("regole", [])

    def avvisi_per(minore):
        return av.db.execute("SELECT COUNT(*) FROM avvisi_tutori WHERE minore = ? AND "
                             "tipo = 'sicurezza' AND tutore = 'carlo'", (minore,)).fetchone()[0]

    prot = G.PROTEZIONE
    # 1. Primo pezzo: da solo non è un pericolo; il secondo pezzo la interrompe con la voce
    #    (livello B acceso fuori dalla protezione: contrario della 3)
    t, detto, regole = turno("Sofia", "Calliope, un signore al parco mi ha detto di andare a "
                                      "casa sua.", modo="voce")
    verifica("primo pezzo da solo: risposta normale, nessun avviso",
             prot not in detto and avvisi_per("sofia") == 0, str(detto))
    verifica("contrario: fuori dalla protezione la voce di chi è registrato interrompe",
             ascolto.voice_ok == [True] and t.watch.get("seed") is not None,
             str(ascolto.voice_ok))
    # 2. Secondo pezzo, detto interrompendo: giudicato unito al primo
    t, detto, regole = turno("Sofia", "E di non dirlo alla mamma.", barged=True, modo="voce")
    verifica("pezzo detto interrompendo: il guardiano giudica la frase unita",
             "signore" in guardia.domande[-1] and "non dirlo" in guardia.domande[-1]
             and "guardia_pezzi_uniti" in regole, guardia.domande[-1])
    verifica("al modello va solo il pezzo detto (l'unione serve al giudizio)",
             cervello.richieste[-1] == "E di non dirlo alla mamma.", cervello.richieste[-1])
    verifica("pezzi uniti: protezione e un avviso ai tutori",
             detto == [prot] and avvisi_per("sofia") == 1, str(detto))
    # 3. La protezione non si interrompe con la sola voce: detta per intero
    verifica("durante la protezione la sola voce non interrompe (livello B spento)",
             ascolto.voice_ok[-1] is False and prot in voce.ultimo
             and not t.watch.get("seed") and c.protezione_in_corso is False,
             f"{ascolto.voice_ok} dette={voce.ultimo}")
    verifica("la protezione era segnata come in corso mentre si diceva",
             (prot, True) in voce.durante, str(voce.durante[-1:]))
    # 4. Un altro pezzo subito dopo: protezione di nuovo, avviso no
    t, detto, regole = turno("Sofia", "Non dirlo alla mamma, eh.", barged=True)
    verifica("stesso episodio: protezione detta di nuovo, avviso non ripetuto",
             detto == [prot] and avvisi_per("sofia") == 1
             and "avviso_pericolo_ripetuto" in regole
             and any("non lo ripeto" in r for r in righe), f"{detto} {regole}")
    # 5. Contrari dell'avviso
    t, detto, regole = turno("Sofia", "Calliope, voglio farmi del male.")
    verifica("contrario: argomento diverso → avviso nuovo",
             detto == [prot] and avvisi_per("sofia") == 2
             and "avviso_pericolo_ripetuto" not in regole, str(regole))
    t, detto, regole = turno("Luca", "Calliope, un signore mi ha detto di non dirlo alla mamma.")
    verifica("contrario: un altro minore → il suo avviso",
             detto == [prot] and avvisi_per("luca") == 1, str(detto))
    vecchio = (datetime.datetime.now() - datetime.timedelta(seconds=cfg.minori_avviso_ripetuto_s
                                                             + 60)).isoformat(timespec="seconds")
    av.db.execute("UPDATE avvisi_tutori SET creato = ? WHERE minore = 'sofia'", (vecchio,))
    av.db.commit()
    t, detto, regole = turno("Sofia", "Calliope, quel signore ha detto di non dirlo alla mamma.")
    verifica("contrario: finestra passata → avviso di nuovo",
             avvisi_per("sofia") == 3 and "avviso_pericolo_ripetuto" not in regole, str(regole))
    cfg.minori_avviso_ripetuto_s = 0
    t, detto, regole = turno("Sofia", "Calliope, quel signore ha detto di non dirlo alla mamma.")
    verifica("contrario: minori_avviso_ripetuto_s = 0 → ogni volta (come prima)",
             avvisi_per("sofia") == 4, str(regole))
    cfg.minori_avviso_ripetuto_s = 600.0
    # 6. Contrari dell'unione dei pezzi
    turno("Sofia", "Calliope, un signore al parco mi ha detto di andare a casa sua.")
    t, detto, regole = turno("Luca", "E di non dirlo alla mamma.", barged=True)
    verifica("contrario: il pezzo di un'altra persona non si unisce",
             "guardia_pezzi_uniti" not in regole and prot not in detto, guardia.domande[-1])
    turno("Sofia", "Calliope, un signore al parco mi ha detto di andare a casa sua.")
    t, detto, regole = turno("Sofia", "E di non dirlo alla mamma.")
    verifica("contrario: una frase non detta interrompendo non si unisce",
             "guardia_pezzi_uniti" not in regole and prot not in detto, guardia.domande[-1])
    turno("Sofia", "Calliope, un signore al parco mi ha detto di andare a casa sua.")
    p = c.ultima_frase_guardia
    c.ultima_frase_guardia = (p[0], p[1], p[2] - 31.0)
    t, detto, regole = turno("Sofia", "E di non dirlo alla mamma.", barged=True)
    verifica("contrario: oltre UNIONE_PEZZI_S non si unisce",
             "guardia_pezzi_uniti" not in regole and prot not in detto, guardia.domande[-1])
    # 7. Il nome interrompe la protezione: si ripete per intero al turno dopo di Sofia
    c.ultima_frase_guardia = None
    t, detto, regole = turno("Sofia", "Calliope, voglio farmi del male.", modo="nome")
    verifica("il nome interrompe la protezione: da ripetere",
             detto == [prot] and prot not in voce.ultimo and "protezione_interrotta" in regole
             and c.protezione_da_ripetere is not None, f"{regole} dette={voce.ultimo}")
    t, detto, regole = turno("Carlo", "Calliope, che ore sono?")
    verifica("contrario: un'altra persona nel mezzo non la sente",
             prot not in detto and c.protezione_da_ripetere is not None, str(detto))
    t, detto, regole = turno("Sofia", "Calliope, che ore sono?")
    verifica("al turno dopo di Sofia la protezione si ripete per intero, dopo la risposta",
             detto == ["Risposta a «Calliope, che ore sono?».", prot]
             and "protezione_ripetuta" in regole and c.protezione_da_ripetere is None,
             f"{detto} {regole}")
    t, detto, regole = turno("Sofia", "Calliope, che ore sono?")
    verifica("contrario: ripetuta una volta sola",
             prot not in detto and "protezione_ripetuta" not in regole, str(detto))
    t, detto, regole = turno("Sofia", "Calliope, voglio farmi del male.", modo="nome")
    t, detto, regole = turno("Sofia", "Calliope, voglio farmi del male.")
    verifica("contrario: se il turno dopo la dice già per intero, non si ripete due volte",
             detto == [prot] and c.protezione_da_ripetere is None, str(detto))
    # 8. known_voice fuori dalla protezione decide come prima
    c.protezione_in_corso = False
    verifica("known_voice fuori dalla protezione: la voce registrata interrompe",
             c.known_voice(np.zeros(16000, dtype=np.float32)) is True)
    c.protezione_in_corso = True
    verifica("known_voice durante la protezione: continua",
             c.known_voice(np.zeros(16000, dtype=np.float32)) is False)
    c.protezione_in_corso = False
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
