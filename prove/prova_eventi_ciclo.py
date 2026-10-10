"""
Il registro degli eventi in ombra sul ciclo della voce (10/10/2026, passi 0 e 1 del § 8 di
docs/ricerche/2026-10-10-registro-eventi.md): `prova_eventi_proiezione` e la prova dei contatori
del passo 0 su un giro sintetico.

    python prove/prova_eventi_ciclo.py

Un `Ciclo` vero con Brain vero (backend a copione), ascolto, Whisper e voce finti; dal passo 2
ciò che va alla voce lo dice all'ombra l'uscita unica (`calliope/eventi/uscita.py`), con l'atto e
l'autore, come nel ciclo vero. Il giro: una risposta normale,
una risposta interrotta dal nome dopo la prima frase, lo stop, la cortesia, un timer scaduto
(annuncio che oggi non entra nella storia), una frase filtrata per la voce con e senza
l'allineamento della storia, un documento pronto con «Lo apro?» (proposta registrata), la
chiusura dello sviluppo con il testo dopo la domanda (non registrata), il nome da solo («Sì?»).
Per ogni turno: i contatori del passo 0 (`parlato`), le differenze dell'ombra (`eventi_ombra`)
e la garanzia del § 3.1 (il testo proiettato è ciò che si è sentito). Poi le guardie della
latenza: nessuna scrittura su disco fra il modello e la prima frase, l'uscita unica costa
microsecondi, `eventi: spento` non scrive niente. Passo 2: l'autore delle frasi della risposta
(frase pronta di un tool, ripiego, contenuto), la posizione delle chiamate fra le frasi nella
proiezione, la risposta scritta sullo schermo dagli eventi, ogni atto classificato. Nomi di
fantasia, niente rete né audio: ~2 s.
"""
import os
import queue
import sys
import tempfile
import threading
import time
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

from calliope import corsie  # noqa: E402
from calliope.ciclo import Ciclo, Servizi  # noqa: E402
from calliope.cortesia import Cortesia  # noqa: E402
from calliope.eventi import misura, proiezioni  # noqa: E402
from calliope.eventi import ombra as ombra_mod  # noqa: E402
from calliope.eventi.registro import Disco, Registri  # noqa: E402
from calliope.eventi.tipi import ATTI  # noqa: E402

import prova_ciclo as pc  # noqa: E402  (i finti del ciclo)
import prova_stati_buchi as sb  # noqa: E402  (Brain con il backend a copione)

errori = 0


def verifica(nome, ok, info=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({info})" if info and not ok else ""),
          flush=True)


class VoceOsservata(pc.Voce):
    """La voce finta con `played` e l'interruzione come tts.Speaker; `interrompi_dopo`: dopo
    quante frasi sentite arriva il nome (barge-in). Conta i turni della voce."""

    def __init__(self):
        super().__init__()
        self.interrupted = False
        self.interrompi_dopo = None
        self.turno = 0

    def say(self, t):
        self.detto.append(t)
        if self.interrupted:
            return
        if self.interrompi_dopo is not None and len(self.played) >= self.interrompi_dopo:
            self.interrupted = True             # il nome arriva mentre dice questa frase
            return
        self.played.append(t)

    def say_cached(self, t):
        self.detto.append(t)

    def start_turn(self):
        self.played = []
        self.interrupted = False
        self.turno += 1

    def interrupt(self):
        self.interrupted = True

    def saying_name(self):
        return False


class AscoltoNome(pc.Ascolto):
    def __init__(self, voce):
        self.voce = voce

    def watch_for_name(self, wake, stop, saying_name, voice_ok=None):
        while not stop.is_set():
            if self.voce.interrupted:
                return [np.zeros(1600, dtype=np.float32)]
            stop.wait(0.002)
        return [np.zeros(1600, dtype=np.float32)] if self.voce.interrupted else None


def prepara(tmp, copione, modo="ombra", disco_cls=Disco):
    b = sb.brain(copione)
    # Lo sviluppo finto, anche per un ospite (qui conta la domanda, non chi può chiuderlo)
    spec = sb.proponi("sviluppo_finto", "Lo chiudo?", b.fatti)
    spec.levels = frozenset({"ospite", "familiare", "amministra"})
    b.tools.register(spec)
    b.cfg.eventi = modo
    b.cfg.speaker_id_enabled = False
    b.cfg.debug_audio_dir = None
    b.cfg.uscita_controllo = False
    turni = []
    voce = VoceOsservata()
    stt = pc.Whisper()
    scritte = []
    instr = types.SimpleNamespace(dopo_turno=lambda x: x, inizio_voce=lambda: None,
                                  persona=lambda *a: None, origine=lambda: {},
                                  annuncia_verso=lambda *a, **k: None,
                                  risposta_scritta=lambda *a: scritte.append(a) or True,
                                  inizio_scritto=lambda *a: "satellite", scritte=scritte)
    registri = Registri(disco_cls.file(os.path.join(tmp, "conversazioni.db")),
                        log=lambda m: None) if modo != "spento" else None
    srv = Servizi(b.cfg, registry=pc.Persone(), stt=stt, instradamento=instr,
                  cortesia=Cortesia(),
                  turns=types.SimpleNamespace(write=lambda r: turni.append(dict(r))),
                  attiva_minori=lambda: False, enroll_pending=False, eventi=registri)
    srv.barge_in, srv.wake = True, object()
    annunci = types.SimpleNamespace(agenda=queue.Queue(), documenti=queue.Queue(),
                                    installazioni=None, lavori=None, estensioni=None)
    c = Ciclo(srv, corsie.Corsia("locale"), AscoltoNome(voce), voce, pc.ChiParla(), b,
              b.tool_ctx, annunci, None, threading.Event())
    prepara.instr = instr
    return b, c, voce, stt, turni, annunci, registri


def giro(c, stt, frase=None):
    if frase is not None:
        stt.frasi.append(frase)
    return c.giro()


def riga(turni, esito, testo=None):
    for r in reversed(turni):
        if r.get("esito") == esito and (testo is None or testo in str(r.get("testo") or "")):
            return r
    return {}


def motivi(r) -> set:
    return set(((r.get("parlato") or {}).get("motivi") or {}))


def differenze(r) -> set:
    return set(((r.get("eventi_ombra") or {}).get("differenze") or {}))


def prova_giro_sintetico():
    print("— il giro sintetico: passo 0 e proiezione in ombra")
    tmp = tempfile.mkdtemp(prefix="eventi-ciclo-")
    copione = [
        [("text", "Sono le dieci.")],
        [("text", "Venezia è sulla laguna. Ha più di cento isole. È bellissima.")],
        [("text", "Ecco: **mare**.")],
        [("text", "Ecco: **sole**.")],
        sb.chiama("sviluppo_finto", finale="Chiudo lo sviluppo di prova? Se vuoi solo una "
                                           "pausa, dimmi sospendi."),
    ]
    b, c, voce, stt, turni, annunci, registri = prepara(tmp, copione)
    giro(c, stt, "Calliope, che ore sono?")
    voce.interrompi_dopo = 1
    giro(c, stt, "Calliope, raccontami di Venezia.")
    voce.interrompi_dopo = None
    verifica("interruzione: la storia ha la frase sentita e il segno",
             b.history[-1]["content"] == voce.detto[-2] + " … (interrotta)"
             and voce.detto[-1] not in b.history[-1]["content"], b.history[-1]["content"])
    giro(c, stt, "Calliope, basta.")              # dopo l'interruzione: stop
    giro(c, stt, "Calliope, grazie.")             # cortesia
    annunci.agenda.put({"kind": "timer", "label": "della pasta", "due": time.time(),
                        "owner_name": None, "id": 1})
    c.sveglia.set()
    giro(c, stt)                                  # il timer scaduto (annuncio)
    giro(c, stt, "Calliope, scrivi in grassetto la parola mare.")
    b.allinea_detto = None                        # come prima del 10/10: la storia non allineata
    giro(c, stt, "Calliope, scrivi in grassetto la parola sole.")
    del b.allinea_detto
    annunci.documenti.put({"messaggio": "Il documento è pronto. Lo apro?", "owner": None,
                           "in_sospeso": {"domanda": "Lo apro?", "tool": "apri_finto",
                                          "cosa": "aprire il documento",
                                          "argomenti": {"conferma": True}}})
    c.sveglia.set()
    giro(c, stt)                                  # documento pronto, con la domanda
    giro(c, stt, "Calliope, chiudi lo sviluppo.")
    giro(c, stt, "Calliope.")                     # il nome da solo: «Sì?»
    c._scrivi_turno(c.rec)                        # l'ultimo turno nel registro
    c.rec = None

    r = riga(turni, "risposta", "che ore sono")
    verifica("risposta normale: nessun parlato diverso, nessuna differenza dell'ombra",
             not (r.get("parlato") or {}).get("diverso") and not differenze(r)
             and (r.get("eventi_ombra") or {}).get("eventi", 0) >= 4, str(r.get("parlato"))
             + str(r.get("eventi_ombra")))
    r = riga(turni, "risposta", "Venezia")
    verifica("interrotta: passo 0 «interrotta_persa» (la frase a metà sentita e persa)",
             motivi(r) == {"interrotta_persa"}, str(r.get("parlato")))
    verifica("interrotta: la proiezione è la storia (frasi sentite e il segno)",
             not differenze(r), str(r.get("eventi_ombra")))
    r = riga(turni, "interruzione")
    verifica("stop: «Va bene, mi fermo» nella storia e mai detto → stop_non_detto (passo 0 e 1)",
             "stop_non_detto" in motivi(r) and "stop_non_detto" in differenze(r),
             f"{r.get('parlato')} {r.get('eventi_ombra')}")
    r = riga(turni, "cortesia")
    verifica("cortesia: «Prego» nella storia come detto, nessuna differenza",
             not motivi(r) and not differenze(r), f"{r.get('parlato')} {r.get('eventi_ombra')}")
    r = riga(turni, "risposta", "parola mare")
    verifica("timer scaduto fra un turno e l'altro: non nella storia "
             "(non_in_storia:annuncio_agenda), riportato al turno dopo",
             "non_in_storia:annuncio_agenda" in motivi(r)
             and "non_in_storia:annuncio_agenda" in differenze(r)
             and (r.get("parlato") or {}).get("fra_turni") == 1,
             f"{r.get('parlato')} {r.get('eventi_ombra')}")
    verifica("frase filtrata con la storia allineata (_storia_come_detta): niente filtri_frase",
             "filtri_frase" not in motivi(r) and "filtri_frase" not in differenze(r),
             str(r.get("parlato")))
    r = riga(turni, "risposta", "parola sole")
    verifica("frase filtrata senza allineamento: filtri_frase (passo 0 e 1)",
             "filtri_frase" in motivi(r) and "filtri_frase" in differenze(r),
             f"{r.get('parlato')} {r.get('eventi_ombra')}")
    r = riga(turni, "risposta", "chiudi lo sviluppo")
    p = r.get("parlato") or {}
    verifica("documento pronto «Lo apro?»: domanda registrata (proposta), riportata",
             p.get("domande_registrate") == 1, str(p))
    verifica("«Chiudo lo sviluppo…? Se vuoi solo una pausa…»: domanda non registrata, "
             "testo_dopo_la_domanda",
             p.get("domande_non_registrate") == 1
             and p.get("domande_motivi") == {"testo_dopo_la_domanda": 1}, str(p))
    r = riga(turni, "saluto")
    p = r.get("parlato") or {}
    verifica("nome da solo: «Sì?» fuori dalla storia (non_in_storia:saluto, domanda "
             "fuori_dalla_storia)",
             "non_in_storia:saluto" in motivi(r)
             and p.get("domande_motivi") == {"fuori_dalla_storia": 1}, str(p))

    # La garanzia del § 3.1: per ogni turno il testo proiettato, tolto il segno, è la
    # concatenazione delle frasi sentite registrate (attese escluse)
    reg = registri.della_corsia(b.conv.chiave)
    vista = proiezioni.turni(reg.eventi())
    ok = all(misura.senza_segno(proiezioni.testo_assistente(x))
             == " ".join(t for t, *_ in proiezioni.detto(x)) for x in vista["turni"])
    verifica("garanzia: testo proiettato = frasi sentite, turno per turno", ok)
    msgs = proiezioni.messaggi(vista)
    utenti_p = [m["content"] for m in msgs if m["role"] == "user"]
    utenti_s = [m["content"] for m in b.history if m.get("role") == "user"]
    verifica("le frasi della persona proiettate sono quelle della storia",
             utenti_p == utenti_s, f"{utenti_p} {utenti_s}")
    verifica("nessuna fuga nella proiezione", proiezioni.fughe(reg.eventi(), msgs) == 0)
    tot = {}
    for r in turni:
        for k, v in ((r.get("eventi_ombra") or {}).get("differenze") or {}).items():
            tot[k] = tot.get(k, 0) + v
    verifica("differenze dell'ombra solo dei meccanismi attesi (ognuna contata una volta)",
             set(tot) <= {"stop_non_detto", "non_in_storia:annuncio_agenda", "filtri_frase",
                          "non_in_storia:saluto"}
             and all(v == 1 for v in tot.values()), str(tot))
    ms = [r["eventi_ombra"]["contesto_ms"] for r in turni if r.get("eventi_ombra")]
    verifica("contesto_ms in ogni turno, sotto i 20 ms", ms and max(ms) < 20, str(ms))
    by = [r["eventi_ombra"].get("byte", 0) for r in turni if r.get("eventi_ombra")]
    print(f"    misura: contesto_ms massimo {max(ms):.2f}, byte per turno mediana "
          f"{sorted(by)[len(by) // 2]}, massimo {max(by)}")
    rias = misura.riassunto(turni)
    giorno = next(iter(rias.values()))
    testo = misura.testo(rias)
    verifica("calliope stato --turni: la sezione con gli avvisi (parlato e domande)",
             giorno["parlato_diverso"] >= 4 and giorno["domande_non_registrate"] == 2
             and "ATTENZIONE: in" in testo and "domande dette senza una proposta" in testo,
             testo)
    registri.disco.db.close()


def _turno_storia(history, frase):
    """I messaggi della storia di Brain dal messaggio della persona `frase` al prossimo."""
    i = next(i for i, m in enumerate(history) if m.get("role") == "user"
             and frase in str(m.get("content") or ""))
    j = next((k for k in range(i + 1, len(history)) if history[k].get("role") == "user"),
             len(history))
    return history[i:j]


def _forma(msgs):
    """Ruoli, testi e chiamate (la forma dei risultati la confronta già l'ombra)."""
    return [(m.get("role"), "" if m.get("role") == "tool" else str(m.get("content") or "").strip(),
             [c.get("name") for c in m.get("tool_calls") or ()]) for m in msgs]


def prova_passo2():
    print("— passo 2: autore e atto all'invio, chiamate fra le frasi, risposta scritta, atti")
    tmp = tempfile.mkdtemp(prefix="eventi-passo2-")
    copione = [
        sb.chiama("sviluppo_finto", finale="Ho fatto il passo dello sviluppo di prova."),
        [("text", "Guardo subito che ore sono, un attimo solo. "),
         ("calls", [{"id": "call_0", "name": "ora_attuale", "arguments": {}}])],
        [("text", "Sono le dieci in punto, buona mattinata.")],
        [("text", "…")], [("text", "…")],
        [("text", "Venezia è una città costruita sulla laguna.")],
    ]
    b, c, voce, stt, turni, annunci, registri = prepara(tmp, copione)
    giro(c, stt, "Calliope, fai il passo dello sviluppo.")
    giro(c, stt, "Calliope, che ore sono?")
    giro(c, stt, "Calliope, dimmi qualcosa.")
    # Una frase scritta da uno schermo: la risposta scritta viene dall'uscita unica
    scritto = {"tipo": "scritto", "testo": "Calliope, parlami di Venezia.", "schermo": "tavolo",
               "schermo_id": 1}

    def prendi_scritto(t):
        t.scritto = dict(scritto)
        c.uscita.persona(scritto=True)
    c._prendi_scritto = prendi_scritto
    c.s.registry.by_id = lambda i: None
    giro(c, stt)
    del c._prendi_scritto
    c._scrivi_turno(c.rec)
    c.rec = None
    reg = registri.della_corsia(b.conv.chiave)
    detti = [e for e in reg.eventi() if e.tipo == "detto_calliope"]

    def detto(testo):
        return next((e.dati for e in detti if testo in e.dati.get("testo", "")), {})
    d = detto("Ho fatto il passo")
    verifica("la frase pronta di un tool: autore «esito» scritto all'invio (Brain la marca)",
             d.get("autore") == "esito" and d.get("atto") == "risposta", str(d))
    d = detto("Non ci sono riuscita")
    verifica("il ripiego di Brain: autore «atto», atto «ripeti»",
             d.get("autore") == "atto" and d.get("atto") == "ripeti", str(d))
    d1, d2 = detto("Guardo subito"), detto("Sono le dieci")
    verifica("il contenuto del modello: autore «contenuto», atto «risposta»",
             d2.get("autore") == "contenuto" and d2.get("atto") == "risposta", str(d2))
    verifica("la posizione fra le chiamate: la frase prima del tool 0, quella dopo 1",
             d1.get("dopo_chiamate") == 0 and d2.get("dopo_chiamate") == 1, f"{d1} {d2}")
    chiamate = [e.dati for e in reg.eventi() if e.tipo == "chiamata_tool"
                and e.dati.get("nome") == "ora_attuale"]
    verifica("la chiamata con la sua passata del modello", chiamate
             and chiamate[-1].get("passata") == 0, str(chiamate))
    # La proiezione del turno con il tool = la storia di Brain, messaggio per messaggio
    vista = proiezioni.turni(reg.eventi())
    x = next(t for t in vista["turni"] if "che ore sono" in str(t["persona"]))
    msgs = proiezioni.messaggi({"riassunto": None, "turni": [x]})
    storia = _turno_storia(b.history, "che ore sono")
    verifica("la frase detta prima del tool è il testo del messaggio con la chiamata, come "
             "nella storia (prima la proiezione la metteva dopo i risultati)",
             _forma(msgs) == _forma(storia), f"{_forma(msgs)} ≠ {_forma(storia)}")
    r = riga(turni, "risposta", "che ore sono")
    verifica("…e l'ombra non vede differenze in quel turno", not differenze(r),
             str(r.get("eventi_ombra")))
    # La risposta scritta sullo schermo dagli eventi
    ultimo = voce.detto[-1]
    sc = [a for a in prepara.instr.scritte if a and a[0] and a[0].get("schermo") == "tavolo"]
    verifica("risposta scritta sullo schermo: le frasi dell'uscita unica",
             sc and sc[-1][2] == ultimo, f"{sc} {voce.detto[-2:]}")
    d = detto("Venezia è una città")
    verifica("…con il canale «scritto» nel detto_calliope", d.get("canale") == "scritto", str(d))
    # Ogni atto classificato: nessun motivo non_in_storia fuori dall'elenco, nessun atto ignoto
    motivi_tutti = set()
    for t in turni:
        motivi_tutti |= set(((t.get("parlato") or {}).get("motivi") or {}))
        motivi_tutti |= set(((t.get("eventi_ombra") or {}).get("differenze") or {}))
    verifica("ogni atto detto è nell'elenco chiuso (tipi.ATTI)",
             all(e.dati.get("atto") in ATTI for e in detti),
             str({e.dati.get("atto") for e in detti} - set(ATTI)))
    verifica("nessun motivo «non_in_storia» senza classe",
             all(misura.atteso(m) for m in motivi_tutti), str(motivi_tutti))
    registri.disco.db.close()


def prova_turni_della_voce():
    print("— passo 2: nessuna frase fuori turno (correzione del quarto giro, nell'uscita)")
    tmp = tempfile.mkdtemp(prefix="eventi-turni-")
    b, c, voce, stt, turni, annunci, registri = prepara(tmp, [[("text", "Sono le dieci.")]])
    # Corsia nuova (voce al turno 0): «Sì?» al nome da solo, senza un turno aperto prima
    c.uscita._aperto = False
    voce.turno = 0
    c.uscita.di("Sì?", "saluto")
    verifica("un atto al turno 0 apre un turno della voce prima di dirlo",
             voce.turno == 1 and voce.detto[-1] == "Sì?", f"{voce.turno} {voce.detto}")
    # Un turno fermato da un'interruzione: l'atto ne apre uno nuovo, la risposta no
    voce.interrupted = True
    c.uscita.di("Scusa, ho avuto un problema.", "errore")
    verifica("un atto in un turno interrotto apre un turno nuovo (e l'interruzione si azzera)",
             voce.turno == 2 and not voce.interrupted, str(voce.turno))
    voce.interrupted = True
    c.uscita.di("Una frase della risposta.", "risposta")
    verifica("contrario: le parole di una risposta interrotta restano nel suo turno (la voce le "
             "scarta come prima)", voce.turno == 2 and voce.interrupted, str(voce.turno))
    voce.interrupted = False
    c.uscita.di("Ancora una frase.", "registrazione")
    verifica("contrario: un atto in un turno aperto e non fermato non ne apre un altro",
             voce.turno == 2, str(voce.turno))
    registri.disco.db.close()


class DiscoSorvegliato(Disco):
    """Un disco che si ricorda se qualcuno gli scrive mentre il modello sta rispondendo."""
    in_risposta = False
    violazioni = 0

    def accoda(self, ev):
        if DiscoSorvegliato.in_risposta:
            DiscoSorvegliato.violazioni += 1
        super().accoda(ev)

    def scrivi(self):
        if DiscoSorvegliato.in_risposta:
            DiscoSorvegliato.violazioni += 1
        super().scrivi()


def prova_latenza():
    print("— latenza: niente disco fra il modello e la prima frase; l'osservatore costa poco")
    tmp = tempfile.mkdtemp(prefix="eventi-lat-")
    b, c, voce, stt, turni, annunci, registri = prepara(
        tmp, [[("text", "Uno. Due. Tre.")] for _ in range(3)], disco_cls=DiscoSorvegliato)
    stream = b.backend.stream

    def stream_sorvegliato(messages, tools):
        DiscoSorvegliato.in_risposta = True
        yield from stream(messages, tools)
    b.backend.stream = stream_sorvegliato
    say = voce.say

    def say_sorvegliata(t):
        DiscoSorvegliato.in_risposta = False      # la prima frase è partita
        say(t)
    voce.say = say_sorvegliata
    for f in ("Calliope, conta fino a tre.", "Calliope, ancora.", "Calliope, di nuovo."):
        giro(c, stt, f)
    c._scrivi_turno(c.rec)
    verifica("nessuna scrittura del registro fra la richiesta al modello e la prima frase",
             DiscoSorvegliato.violazioni == 0, str(DiscoSorvegliato.violazioni))
    verifica("…ma gli eventi sono su disco a turno finito",
             registri.disco.scritti > 0, str(registri.disco.scritti))
    # Il costo dell'uscita unica per frase (il detto in memoria e l'ombra che lo sente), senza
    # la voce: con una voce che non fa niente
    o = c.ombra
    u = c.uscita
    voce_vera = u.speaker
    u.speaker = types.SimpleNamespace(say=lambda t: None, say_cached=lambda t: None,
                                      start_turn=lambda: None, played=[], interrupted=False,
                                      muto=False)
    n = 3000
    t0 = time.perf_counter()
    for _ in range(n):
        u.di("Una frase qualunque di prova.", "risposta")
    us = (time.perf_counter() - t0) / n * 1e6
    u.speaker = voce_vera
    o._finestra.clear()
    print(f"    misura: uscita unica {us:.1f} µs per frase (detto in memoria e ombra)")
    verifica("l'uscita unica costa meno di 100 µs per frase", us < 100, f"{us:.1f} µs")
    # Il confronto (in cima al giro dopo, la voce ha già finito) non tocca la prima frase
    registri.disco.db.close()
    # eventi: spento → nessuna ombra, nessun campo nuovo nel registro dei turni
    tmp2 = tempfile.mkdtemp(prefix="eventi-spento-")
    b2, c2, voce2, stt2, turni2, _a, reg2 = prepara(tmp2, [[("text", "Sono le dieci.")]],
                                                   modo="spento")
    giro(c2, stt2, "Calliope, che ore sono?")
    c2._scrivi_turno(c2.rec)
    verifica("eventi: spento → niente ombra, niente parlato né eventi_ombra, come prima",
             c2.ombra is None and reg2 is None and c2.uscita.osservatore is None
             and not any("parlato" in r or "eventi_ombra" in r for r in turni2),
             str(turni2[-1:]))
    verifica("…e la risposta è la stessa", voce2.detto == ["Sono le dieci."], str(voce2.detto))


def prova_modo():
    print("— l'interruttore: spento | ombra; attivo rifiutato")
    from calliope.config import _eventi_valido
    verifica("«ombra» e «spento» valgono", _eventi_valido("Ombra") == "ombra"
             and _eventi_valido("spento") == "spento")
    try:
        _eventi_valido("attivo")
        rifiutato = False
    except ValueError as e:
        rifiutato = "passo 3" in str(e)
    verifica("«attivo» rifiutato (passo 3, resta «ombra»)", rifiutato)
    cfg = types.SimpleNamespace(eventi="attivo")
    verifica("un «attivo» passato a mano vale «ombra»", ombra_mod.modo(cfg) == "ombra")


def prova_taglio_e_compressione():
    print("— taglio in testa e compressione: la finestra della proiezione segue la storia")
    tmp = tempfile.mkdtemp(prefix="eventi-taglio-")
    b, c, voce, stt, turni, annunci, registri = prepara(
        tmp, [sb.chiama("ora_attuale"), [("text", "Sono le dieci.")]]
        + [[("text", f"Risposta numero {i}.")] for i in range(1, 6)])
    for i in range(3):
        giro(c, stt, f"Calliope, domanda numero {i}.")
    b._c().togli_in_testa(2)                      # come _trim_history: via i primi turni
    giro(c, stt, "Calliope, domanda numero 3.")
    b._c().togli_in_testa(2)
    b._c().riassunto = {"tipo": "compressione", "testo": "Riassunto: domande numerate.",
                        "quando": time.time()}
    giro(c, stt, "Calliope, domanda numero 4.")
    giro(c, stt, "Calliope, domanda numero 5.")
    c._scrivi_turno(c.rec)
    c.rec = None
    tot = {}
    for r in turni:
        for k, v in ((r.get("eventi_ombra") or {}).get("differenze") or {}).items():
            tot[k] = tot.get(k, 0) + v
    ore = [m for m in registri.della_corsia(b.conv.chiave).eventi() if m.tipo == "esito_tool"]
    verifica("il risultato di ora_attuale nel registro (poi «di allora» nella proiezione)",
             len(ore) == 1, str(ore))
    verifica("dopo il taglio e la compressione nessuna differenza (finestra, riassunto, forma "
             "dei risultati)",
             not tot and not any((r.get("eventi_ombra") or {}).get("non_osservati")
                                 for r in turni), str(tot))
    reg = registri.della_corsia(b.conv.chiave)
    comp = [e for e in reg.eventi() if e.tipo == "compressione"]
    verifica("l'evento compressione con il riassunto e fino_a", len(comp) == 1
             and comp[0].dati["riassunto"] == "Riassunto: domande numerate."
             and comp[0].dati["fino_a"] > 0, str(comp))
    msgs = proiezioni.contesto(reg.eventi())
    utenti = [m["content"] for m in msgs if m["role"] == "user"]
    verifica("la proiezione dopo la compressione: il riassunto e i turni dopo il taglio",
             msgs[0]["content"] == "Riassunto: domande numerate."
             and utenti == [m["content"] for m in b.history if m.get("role") == "user"],
             f"{utenti}")
    registri.disco.db.close()


def main():
    prova_modo()
    prova_taglio_e_compressione()
    prova_giro_sintetico()
    prova_passo2()
    prova_turni_della_voce()
    prova_latenza()
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
