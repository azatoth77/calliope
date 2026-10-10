"""
I dieci stati del dialogo che rischiano di non essere gestiti (10/10/2026, «passo 0» della
macchina a stati: docs/ricerche/2026-10-10-macchina-stati.md, § 1.10 e § 8).

    python prove/prova_stati_buchi.py

Una sezione per caso, a secco, con i finti che esistono (Brain con un backend a copione, il
ciclo di prova_ciclo, i cancelli dei minori con orologi finti). Due tipi di verifica:

- `buco(...)`: il buco è confermato con il codice di oggi e la prova **documenta il
  comportamento sbagliato**, segnato «atteso da correggere» con il passo della macchina che lo
  chiuderà. Non fa fallire l'hook finché il comportamento resta quello; quando un passo lo
  corregge la prova fallisce, e va trasformata in una verifica normale con i suoi contrari.
- `verifica(...)`: i buchi corretti dal passo 0 (3, 6, 9, 10), con i contrari.

Nomi e dati di fantasia. Niente rete, audio né modelli: ~2 s.
"""
import json
import os
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calliope import cancelli as cancelli_mod, conferme as C, corsie  # noqa: E402
from calliope.agenti.servizio import Lavori  # noqa: E402
from calliope.brain import Brain, proposta_altrui  # noqa: E402
from calliope.ciclo import Ciclo, Servizi  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.conversazione import Conversazione  # noqa: E402
from calliope.cortesia import Cortesia  # noqa: E402
from calliope.speaker_id import SpeakerContext  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext, ToolSpec  # noqa: E402
from calliope.wakeword import risposta_al_nome  # noqa: E402

import prova_ciclo as pc  # noqa: E402  (i finti del ciclo)

errori = 0
buchi = []


def verifica(nome, ok, info=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({info})" if info and not ok else ""),
          flush=True)


def buco(n: int, nome: str, riprodotto: bool, passo: str, info=""):
    """Un buco confermato: il comportamento sbagliato di oggi, atteso da correggere al `passo`.
    Se non si riproduce più, la prova fallisce: il buco è chiuso e la prova va aggiornata."""
    global errori
    if riprodotto:
        buchi.append(n)
        print(f"BUCO {n} (atteso da correggere: {passo}): {nome}", flush=True)
    else:
        errori += 1
        print(f"ERR buco {n} non più riprodotto ({passo}): {nome} — è chiuso? trasforma la "
              f"prova in una verifica con i contrari  ({info})", flush=True)


# ─────────────────────────── finti per Brain ───────────────────────────
class Prof:
    def __init__(self, nome, admin=False):
        self.name, self.id, self.admin = nome, nome.lower() + "-id", admin
        self.preferred_tone = None


class Persone:
    """SpeakerRegistry per SpeakerContext e speakers del ToolContext (nomi di fantasia)."""

    def __init__(self):
        self.cfg = Config()
        self.users = {"Dario": Prof("Dario", True), "Bianca": Prof("Bianca")}

    def get(self, n):
        return self.users.get(n)


class BackendFinto:
    def __init__(self, copione):
        self.copione = list(copione)
        self.visti = []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        yield from (self.copione.pop(0) if self.copione else [("text", "Va bene.")])


def chiama(nome, **argomenti):
    return [("calls", [{"id": f"c-{nome}", "name": nome, "arguments": argomenti}])]


def frase(sc, nome, come="voce", punteggio=0.7, in_session=True):
    sc.identified_by = come
    sc.from_session = come in ("breve", "conversazione")
    sc.current_speaker = nome
    sc.aggiorna_conversazione(nome, come, in_session, punteggio)


def proponi(nome, domanda, fatti):
    """Un tool d'azione che propone con una domanda e fa solo con conferma=True."""
    def f(ctx, conferma=False, finale=None, **a):
        if conferma:
            fatti.append(nome)
            return {"ok": True, "conferma": "Fatto."}
        return {"ok": True, "fatto": "proposta", "risposta_finale": finale or domanda,
                "in_sospeso": {"domanda": domanda, "tool": nome, "cosa": nome.replace("_", " "),
                               "argomenti": {"conferma": True}}}
    # «sicuro» per la politica: qui conta lo stato della proposta, non chi può farla
    return ToolSpec(name=nome, description="", parameters={}, func=f, risk="azione",
                    classe="sicuro", levels=frozenset({"familiare", "amministra"}))


def brain(copione, lavori=None, agenti=False):
    p = Persone()
    b = Brain.__new__(Brain)
    b.cfg = p.cfg
    b.cfg.llm_num_ctx = 16384
    b.tools = build_registry(agenti=agenti)
    b.fatti = []
    b.tools.register(proponi("apri_finto", "La apro?", b.fatti))
    b.tools.register(proponi("cancella_finto", "Lo cancello?", b.fatti))
    b.history = []
    b.tool_ctx = ToolContext(cfg=p.cfg, speakers=p, speaker_ctx=SpeakerContext(p), speaker=None,
                             lavori=lavori)
    b.backend = BackendFinto(copione)
    b.archivio_conv = b.compressore = None
    b.luogo_fn = lambda: "locale"
    return b


def di(b, testo, chi="Dario", come="voce", livello=None):
    sc = b.tool_ctx.speaker_ctx
    frase(sc, chi, come)
    return "".join(b.stream_reply(testo, livello or sc.current_level))


def interrotta(b, testo, chi="Dario"):
    """Una risposta interrotta dopo il primo pezzo (barge-in, o il guardiano che chiude lo stream
    per dire il cancello 1)."""
    sc = b.tool_ctx.speaker_ctx
    frase(sc, chi, "voce")
    g = b.stream_reply(testo, sc.current_level)
    primo = next(g, "")
    g.close()
    return primo


def sistema(visti) -> str:
    return " ".join(m.get("content") or "" for m in visti if m.get("role") == "system")


# ─────────────────────────── 1. proposta interrotta, stop ───────────────────────────
def caso_1():
    print("— 1. proposta detta e interrotta; stop dopo l'interruzione")
    b = brain([chiama("apri_finto"), chiama("cancella_finto")])
    d1 = di(b, "Calliope, cerca la foto del mare")
    verifica("proposta di prima: «La apro?» in sospeso", d1 == "La apro?"
             and (b.pending or {}).get("tool") == "apri_finto", d1)
    interrotta(b, "Calliope, e il documento vecchio?")
    buco(1, "la proposta nuova («Lo cancello?») detta e interrotta si perde, resta viva quella "
            "di prima", (b.pending or {}).get("tool") == "apri_finto",
         "passo 3 (la proposta nasce anche da una risposta interrotta dopo la domanda)",
         str(b.pending))
    b.record_stop("Calliope, ok")
    buco(1, "lo stop dopo l'interruzione scrive «argomento chiuso» ma la proposta resta valida",
         "argomento chiuso" in b.history[-1]["content"] and b.has_pending(),
         "passo 3 (lo stop chiude la proposta)")


# ─────────────────────────── 2. domande che non sono proposte ───────────────────────────
def caso_2():
    print("— 2. domande che non sono proposte (cancello 1, sviluppo, «Fermo anche il lavoro?»)")
    # Il «sì» al cancello 1 («Va tutto bene?», detto al posto della risposta: il guardiano chiude
    # lo stream) arriva al modello come risposta alla proposta di prima
    b = brain([chiama("apri_finto"), [("text", "Mi dispiace.")], [("text", "Bene.")]])
    di(b, "Calliope, cerca la foto della gita")
    interrotta(b, "Calliope, ho paura")
    di(b, "Sì, va tutto bene.")
    buco(2, "il «sì» al cancello 1 arriva al modello come consenso alla proposta di prima "
            "(«Azione in sospeso … La apro?»)",
         "Azione in sospeso" in sistema(b.backend.visti[-1])
         and "apri_finto" in sistema(b.backend.visti[-1]),
         "passo 3 (il cancello ha priorità e chiude la proposta: proposta_persa_cancello)")

    # La cortesia risponde al posto del cancello 2: «grazie» dopo «Va tutto bene?» riceve
    # «Prego» e il segnale resta aperto senza il secondo giudizio
    cfg = Config()
    cfg.speaker_id_enabled = cfg.barge_in_enabled = cfg.uscita_controllo = False
    cfg.debug_audio_dir = None
    turni = []
    stt, voce, chi, cervello, persone = (pc.Whisper(), pc.Voce(), pc.ChiParla(), pc.Cervello(),
                                         pc.Persone())
    instr = types.SimpleNamespace(dopo_turno=lambda x: x, inizio_voce=lambda: None,
                                  persona=lambda *a: None, origine=lambda: {},
                                  annuncia_verso=lambda *a, **k: None,
                                  risposta_scritta=lambda *a: None)
    giudizi = []
    guardiano = types.SimpleNamespace(verifica=lambda primo, risp: giudizi.append(risp))
    cancelli = cancelli_mod.Cancelli(cfg, log=lambda m: None, avvisi=types.SimpleNamespace(
        manda=lambda *a, **k: 1, registry=None))
    srv = Servizi(cfg, registry=persone, stt=stt, instradamento=instr, cortesia=Cortesia(),
                  turns=types.SimpleNamespace(write=lambda r: turni.append(dict(r))),
                  attiva_minori=lambda: False, biblioteca=object(), enroll_pending=False,
                  guardiano=guardiano, cancelli=cancelli)
    annunci = types.SimpleNamespace(agenda=__import__("queue").Queue(), documenti=None,
                                    installazioni=None, lavori=None, estensioni=None)
    c = Ciclo(srv, corsie.Corsia("locale"), pc.Ascolto(), voce, chi, cervello,
              types.SimpleNamespace(), annunci, None, threading.Event())
    seg = cancelli.apri(Prof("Tommaso"), "frase di prova", ("pericolo",), True, "locale")
    stt.frasi.append("Calliope, grazie.")
    n = len(voce.detto)
    c.giro()
    detto = voce.detto[n:]
    buco(2, "la cortesia («Prego») risponde al posto del cancello 2: il segnale resta aperto e "
            "il secondo giudizio non c'è",
         c.rec.get("esito") == "cortesia" and seg.aperto and not giudizi,
         "passo 3 (priorità: minori come pavimento prima della cortesia)", f"{detto} {giudizi}")
    stt.frasi.append("Calliope, ho paura del buio stasera.")
    c.giro()
    verifica("contrario: una frase che non è cortesia arriva al cancello 2", giudizi
             == ["ho paura del buio stasera."] or bool(giudizi), str(giudizi))
    cancelli.chiudi(seg, "fine prova")
    # Sviluppo («Con cosa provo?», sviluppo_chiedi) e «Fermo anche il lavoro?»: non passano da
    # `pending` (has_pending False); la cortesia le vede solo se sono l'ultima frase della
    # storia (ultima_domanda). Confermato dal codice, il caso del cancello sopra è lo stesso


# ─────────────────────────── 3. «no» a una domanda dell'agente ───────────────────────────
class LavoriFinti:
    """Il minimo del servizio dei lavori per lavoro_rispondi (calliope/agenti/servizio.py)."""

    def __init__(self):
        self.lav = types.SimpleNamespace(id="L7", titolo="Il foglio delle spese",
                                         domanda="Vuoi che lo salvi anche in PDF?",
                                         persona="dario-id", stato="in_attesa")
        self.risposte = []

    def trova_in_attesa(self, persona, lavoro, admin=False):
        if self.lav.stato != "in_attesa":
            return None, "Nessun lavoro aspetta una risposta.", False
        return self.lav, "", False

    def in_attesa(self):
        return [self.lav] if self.lav.stato == "in_attesa" else []

    def rispondi(self, lav, testo):
        self.risposte.append(testo)
        lav.stato = "in_corso"
        return "Grazie, lo dico all'agente: riprende il lavoro."


def caso_3():
    print("— 3. «no» a una domanda sì/no dell'agente (corretto dal passo 0)")
    svc = LavoriFinti()
    b = brain([chiama("lavoro_rispondi", lavoro="L7", risposta="no"), [("text", "Va bene.")]],
              lavori=svc, agenti=True)
    frase(b.tool_ctx.speaker_ctx, "Dario")
    b.record_announcement("Dario, per «Il foglio delle spese» l'agente chiede: vuoi che lo salvi "
                          "anche in PDF?", Lavori.offerta_risposta(None, svc.lav), fonte=None)
    detto = di(b, "No.")
    regole = b.rules_fired()
    verifica("«no» alla domanda dell'agente: arriva all'agente con lavoro_rispondi, il lavoro "
             "riprende", svc.risposte == ["no"] and svc.lav.stato == "in_corso"
             and "risposta_non_rifiuto" in regole and "proposta_rifiutata" not in regole
             and "politica_proposta_rifiutata" not in regole, f"{detto} {regole}")
    verifica("…e non resta un rifiuto di lavoro_rispondi nella conversazione",
             not getattr(b._c(), "rifiutate", None), str(getattr(b._c(), "rifiutate", None)))
    # Contrario: un «no» a una proposta normale («La apro?») resta un rifiuto
    b = brain([chiama("apri_finto"), [("text", "Va bene, non la apro.")]])
    di(b, "Calliope, cerca la foto del mare")
    di(b, "No.")
    verifica("contrario: «no» a «La apro?» chiude la proposta ed è un rifiuto",
             b.pending is None and "proposta_rifiutata" in b.rules_fired()
             and [r.get("tool") for r in b._c().rifiutate] == ["apri_finto"],
             str(b.rules_fired()))


# ─────────────────────────── 4. offerte dei servizi dopo la chiusura ───────────────────────────
def caso_4():
    print("— 4. offerte dei servizi dopo la chiusura della conversazione")
    b = brain([])
    di(b, "Calliope, scrivimi un programma per le foto")
    svc = Lavori.__new__(Lavori)
    svc.cfg, svc._lock, svc._offerte = b.cfg, threading.Lock(), {}
    svc.proposta = lambda lav: "Procedo?"
    svc._interrotti_da_rifare = lambda persona: None
    lav = types.SimpleNamespace(id="L3", persona="dario-id", tipo="codice")
    svc.proponi(lav, b.turn_number)
    b.end_conversation("nuova")
    off = svc.offerta("dario-id", b.turn_number + 1)
    buco(4, "l'offerta del servizio dei lavori sopravvive alla chiusura della conversazione "
            "(il «sì» del turno dopo arriva senza la domanda)",
         b.pending is None and off is not None and off["lavoro"] is lav,
         "passo 5 (le offerte dei servizi sull'orologio della proposta; la chiusura le chiude)",
         str(off))
    # sv.proposto dello sviluppo: non scade (tools/sviluppo._proposta_scaduta lo accetta come
    # «avanti» anche dopo, per scelta dell'08/10): confermato dal codice, non provato qui


# ─────────────────────────── 5. proposta nata da un annuncio ───────────────────────────
def caso_5():
    print("— 5. proposta nata da un annuncio, intestata all'ultimo che ha parlato")
    b = brain([[("text", "Va bene.")]])
    di(b, "Calliope, che ore sono?", chi="Bianca")          # l'ultima voce sul satellite
    b.record_announcement("Dario, il documento è pronto. Lo apro?",
                          {"domanda": "Lo apro?", "tool": "apri_finto", "cosa": "il documento",
                           "argomenti": {"conferma": True}}, fonte=None)
    intestata = (b.pending or {}).get("chi")
    di(b, "Sì.", chi="Dario")
    regole = b.rules_fired()
    buco(5, "l'annuncio per Dario finisce intestato a Bianca: al «sì» di Dario la proposta "
            "risulta di Bianca e non vale", intestata == "bianca-id"
         and ("sospeso_altra_persona" in regole or "sospeso_altrui_consenso" in regole)
         and "Azione in sospeso" not in sistema(b.backend.visti[-1]),
         "passo 5 (annunci intestati a item[\"chi\"])", f"{intestata} {b.rules_fired()}")


# ─────────────────────────── 6. la coda della conversazione ───────────────────────────
def caso_6():
    print("— 6. coda della conversazione dopo una pausa (corretto dal passo 0)")
    # Dario riconosciuto finito nella conversazione anonima del satellite (frase breve)
    b = brain([])
    b.conv = Conversazione("ospite:sat:1")
    di(b, "Che pizza mi consigli stasera?")
    b.end_conversation("conversazione_scaduta")
    verifica("conversazione anonima di un satellite: niente coda nella nuova «ospite:…»",
             b.conv.riassunto is None, str(b.conv.riassunto))
    # Stessa chiave, un'altra persona dopo la pausa: la coda non le arriva
    b = brain([])
    di(b, "Che pizza mi consigli stasera?")
    b.end_conversation("conversazione_scaduta")
    di(b, "Che ore sono?", chi="Bianca")
    verifica("un'altra persona dopo la pausa non riceve la coda di Dario",
             "pizza" not in sistema(b.backend.visti[-1])
             and "conversazione_coda_altra_persona" in b.rules_fired()
             and "conversazione_coda" not in b.rules_fired(), sistema(b.backend.visti[-1])[:200])
    b = brain([])
    di(b, "Che pizza mi consigli stasera?")
    b.end_conversation("conversazione_scaduta")
    di(b, "Che ore sono?", chi=None, livello="ospite")
    verifica("un ospite dopo la pausa non riceve la coda di Dario",
             "pizza" not in sistema(b.backend.visti[-1]), sistema(b.backend.visti[-1])[:200])
    b = brain([])
    di(b, "Che pizza mi consigli stasera?")
    b.end_conversation("conversazione_scaduta")
    di(b, "Cosa ti avevo chiesto?")
    verifica("contrario: la stessa persona la riceve", "pizza" in sistema(b.backend.visti[-1])
             and "conversazione_coda" in b.rules_fired(), str(b.rules_fired()))


# ─────────────────────────── 7. has_pending conta i secondi ───────────────────────────
def caso_7():
    print("— 7. has_pending e proposta_altrui contano i secondi, non i turni")
    b = brain([chiama("apri_finto")])
    di(b, "Calliope, cerca la foto del mare")
    p = b.pending
    b.turn_number = p["turno"] + C.turni_validi(b.cfg)      # la prossima è oltre i turni
    ha, altrui = b.has_pending(), proposta_altrui(p, "bianca-id")
    viva = b._take_pending()
    buco(7, "una proposta morta per i turni conta ancora per has_pending (cortesia, annunci "
            "rinviati) e per proposta_altrui", ha and altrui is not None and viva is None,
         "passo 5 (proposta_valida: tempo e turni in una funzione)", f"{ha} {altrui} {viva}")


# ─────────────────────────── 8. due proposte ───────────────────────────
def caso_8():
    print("— 8. due proposte: vince l'ultima, senza «?» resta la vecchia, il «no» ne chiude una")
    due = [("calls", [{"id": "a", "name": "apri_finto", "arguments": {}},
                      {"id": "b", "name": "cancella_finto", "arguments": {}}])]
    b = brain([due])
    detto = di(b, "Calliope, sistema le foto")
    buco(8, "due proposte nella stessa risposta («La apro? Lo cancello?»): resta solo l'ultima, "
            "la prima si perde in silenzio", detto == "La apro? Lo cancello?"
         and (b.pending or {}).get("tool") == "cancella_finto",
         "passo 2 (la prima chiude la risposta, l'altra diventa un'attesa)", str(b.pending))
    b = brain([chiama("apri_finto"),
               chiama("cancella_finto", finale="Posso cancellarlo, se vuoi.")])
    di(b, "Calliope, cerca la foto del mare")
    di(b, "E il documento vecchio?")
    buco(8, "la proposta nuova senza «?» non la sostituisce: resta viva la vecchia («La apro?»)",
         (b.pending or {}).get("tool") == "apri_finto" and b.has_pending(),
         "passo 2 (proposta_sostituita; una sola proposta parlata)", str(b.pending))
    b = brain([chiama("apri_finto"), [("text", "Va bene.")]])
    di(b, "Calliope, cerca la foto del mare")
    sc = b.tool_ctx.speaker_ctx
    sc.sfida = C.nuova_sfida(b.cfg, "dario-id", "cancella_finto", {"conferma": True})
    di(b, "No.")
    buco(8, "proposta e sfida per tool diversi: il «no» chiude la proposta e lascia la sfida",
         b.pending is None and sc.sfida is not None and sc.sfida.tool == "cancella_finto",
         "passo 2 (la sfida esiste solo per la proposta aperta)", str(sc.sfida))


# ─────────────────────────── 9. il nome vero dopo la registrazione ───────────────────────────
def caso_9():
    print("— 9. «Vuoi dirmi il tuo nome?» (corretto dal passo 0)")
    for testo, atteso in [("Mi chiamo Dario.", ("nome", "Dario")), ("Dario.", ("nome", "Dario")),
                          ("Il mio nome è Maria Rosa.", ("nome", "Maria Rosa")),
                          ("Calliope, sono Luca, grazie.", ("nome", "Luca")),
                          ("Sì.", ("si", None)), ("Sì, certo.", ("si", None)),
                          ("No, grazie.", ("no", None)),
                          ("Che tempo fa domani?", ("altro", None)),
                          ("Sono stanco.", ("altro", None)), ("Ho fame.", ("altro", None)),
                          ("Buongiorno.", ("altro", None))]:
        verifica(f"risposta_al_nome «{testo}» → {atteso}", risposta_al_nome(testo) == atteso,
                 str(risposta_al_nome(testo)))
    cfg = Config()
    cfg.speaker_id_enabled = cfg.barge_in_enabled = cfg.uscita_controllo = False
    cfg.debug_audio_dir = None
    stt, voce, chi, cervello, persone = (pc.Whisper(), pc.Voce(), pc.ChiParla(), pc.Cervello(),
                                         pc.Persone())
    instr = types.SimpleNamespace(dopo_turno=lambda x: x, inizio_voce=lambda: None,
                                  persona=lambda *a: None, origine=lambda: {},
                                  annuncia_verso=lambda *a, **k: None,
                                  risposta_scritta=lambda *a: None)
    srv = Servizi(cfg, registry=persone, stt=stt, instradamento=instr, cortesia=Cortesia(),
                  turns=types.SimpleNamespace(write=lambda r: None),
                  attiva_minori=lambda: False, biblioteca=object(), enroll_pending=False)
    annunci = types.SimpleNamespace(agenda=__import__("queue").Queue(), documenti=None,
                                    installazioni=None, lavori=None, estensioni=None)
    c = Ciclo(srv, corsie.Corsia("locale"), pc.Ascolto(), voce, chi, cervello,
              types.SimpleNamespace(), annunci, None, threading.Event())

    def attesa(s=120.0):
        c.pending_real_name, c._nome_vero_fino = "Primo", time.monotonic() + s

    def giro(testo):
        stt.frasi.append(testo)
        n = len(voce.detto)
        c.giro()
        return voce.detto[n:]

    attesa()
    d = giro("Sì.")
    verifica("«Sì.» non è un nome: chiede il nome e aspetta ancora", d == ["Dimmi pure il tuo "
             "nome."] and not persone.rinominati and c.pending_real_name == "Primo"
             and "nome_vero_si" in c.rec.get("regole", []), str(d))
    d = giro("Mi chiamo Dario.")
    verifica("«Mi chiamo Dario.» → Dario, l'attesa finisce", d == ["Ok, ti chiamerò Dario."]
             and persone.rinominati == [("Primo", "Dario")] and c.pending_real_name is None, str(d))
    persone.rinominati.clear()
    attesa()
    d = giro("Che tempo fa domani?")
    verifica("una frase che non è un nome va al modello (una risposta sola), niente rinomina",
             not persone.rinominati and c.pending_real_name is None
             and cervello.richieste[-1][0] == "Che tempo fa domani?"
             and "nome_vero_al_modello" in c.rec.get("regole", []), str(d))
    attesa(-1)
    c.awake_until = 0.0
    d = giro("Dario.")
    verifica("attesa scaduta: «Dario.» non rinomina più (e senza il nome si ignora)",
             not persone.rinominati and c.pending_real_name is None and d == [], str(d))
    attesa()
    d = giro("No, grazie.")
    verifica("«No, grazie.» chiude l'attesa senza rinominare", d == ["Va bene, ti chiamerò "
             "Primo."] and not persone.rinominati and c.pending_real_name is None, str(d))
    # Un'altra voce riconosciuta (speaker_id acceso): non risponde per la persona registrata
    attesa()
    cfg.speaker_id_enabled = True
    chi.current_speaker = "Bianca"
    c.rec = {}
    esito = c._nome_reale(types.SimpleNamespace(text="Dario."))
    verifica("un'altra persona: la frase non vale come nome", esito is None
             and not persone.rinominati and c.pending_real_name == "Primo"
             and "nome_vero_altra_persona" in c.rec.get("regole", []), str(c.rec))
    chi.current_speaker = "Primo"
    c.rec = {}
    c._nome_reale(types.SimpleNamespace(text="Dario."))
    verifica("contrario: la stessa persona («Primo») sì", persone.rinominati
             == [("Primo", "Dario")], str(persone.rinominati))
    cfg.speaker_id_enabled = False


# ─────────────────────────── 10. segnali dei cancelli dopo un riavvio ───────────────────────────
class Orologi:
    def __init__(self):
        self.m, self.w = 1000.0, 1_800_000_000.0

    def avanti(self, s):
        self.m += s
        self.w += s


def caso_10():
    print("— 10. segnali dei cancelli dei minori dopo un riavvio (corretto dal passo 0)")
    tmp = Path(tempfile.mkdtemp(prefix="calliope-cancelli-"))
    cfg = Config()
    cfg.memory_db = str(tmp / "memoria.db")
    p = cancelli_mod.percorso(cfg)
    verifica("il file sta accanto alla memoria", p == tmp / "cancelli.json", str(p))
    ragazzo = Prof("Tommaso")
    mandati, registro = [], []
    avvisi = types.SimpleNamespace(
        registry=types.SimpleNamespace(users={"Tommaso": ragazzo}),
        manda=lambda prof, tipo, testo, urgente=True, **k: mandati.append(
            (prof.name, tipo, testo, urgente)) or 1)

    def cancelli(o):
        return cancelli_mod.Cancelli(cfg, log=lambda m: None, avvisi=avvisi,
                                     registra=registro.append, orologio=lambda: o.m,
                                     ora=lambda: o.w, percorso=p)

    def spegni(c):
        for s in c.segnali:
            if s.timer is not None:
                s.timer.cancel()

    # Un segnale aperto, Calliope riparte dopo 60 s: riprende con il tempo che restava
    o = Orologi()
    c = cancelli(o)
    c.apri(ragazzo, "frase riservata del ragazzo", ("pericolo",), True, "sat:1")
    salvato = p.read_text(encoding="utf-8")
    verifica("su disco il segnale, senza la frase del minore",
             "Tommaso" in salvato and "frase riservata" not in salvato, salvato[:200])
    spegni(c)
    o.avanti(60)
    c2 = cancelli(o)
    s2 = c2.aperto_per("tommaso-id", None)
    verifica("dopo il riavvio il segnale aperto riprende, con il tempo che restava (240 s)",
             s2 is not None and s2.timer is not None and abs(s2.timer.interval - 240) < 1
             and not mandati, f"{s2} {getattr(getattr(s2, 'timer', None), 'interval', None)}")
    verifica("…il secondo giudizio vede l'argomento al posto della frase",
             s2 is not None and "frase riservata" not in s2.testo and "Tommaso" in s2.testo,
             getattr(s2, "testo", ""))
    verifica("…e la risposta dopo lo trova anche dal satellite (voce incerta)",
             c2.aperto_per(None, "sat:1") is s2)
    spegni(c2)
    # Spenta più a lungo dell'attesa (300 s): vale il silenzio, avviso non urgente
    o.avanti(400)
    c3 = cancelli(o)
    verifica("scaduto durante il riavvio: avviso non urgente «da verificare»",
             len(mandati) == 1 and mandati[0][0] == "Tommaso" and mandati[0][1] == "sicurezza"
             and mandati[0][3] is False and mandati[0][2].startswith("Da verificare"),
             str(mandati))
    verifica("…nel registro dei turni pericolo_silenzio dopo il riavvio",
             registro and registro[-1]["esito"] == "pericolo_silenzio"
             and registro[-1]["pericolo"].get("dopo_riavvio") is True, str(registro[-1:]))
    verifica("…e il segnale resta per la finestra dei due segnali (un secondo dubbio vale "
             "confermato)", c3.aperto_per("tommaso-id", None) is None
             and c3.recente("tommaso-id") is not None)
    c4 = cancelli(o)
    verifica("un altro riavvio non manda di nuovo l'avviso", len(mandati) == 1, str(mandati))
    spegni(c4)
    # Contrari: oltre la finestra il segnale sparisce; senza percorso niente su disco
    o.avanti(cfg.minori_pericolo_finestra_s + 10)
    c5 = cancelli(o)
    verifica("contrario: oltre la finestra dei due segnali non resta niente",
             c5.recente("tommaso-id") is None and not c5.segnali)
    tmp2 = Path(tempfile.mkdtemp(prefix="calliope-cancelli-"))
    c6 = cancelli_mod.Cancelli(cfg, log=lambda m: None, avvisi=avvisi)
    spegni_s = c6.apri(ragazzo, "x", ("pericolo",), True, "sat:1")
    spegni_s.timer.cancel()
    verifica("contrario: senza percorso (prove, terminale) niente su disco",
             c6.percorso is None and not list(tmp2.iterdir()))
    cfg.memory_db = None
    verifica("contrario: senza memory_db nessun percorso", cancelli_mod.percorso(cfg) is None)
    # Un file rovinato non ferma i cancelli
    p.write_text("{rovinato", encoding="utf-8")
    c7 = cancelli_mod.Cancelli(Config(), log=lambda m: None, avvisi=avvisi, percorso=p)
    verifica("file rovinato: si riparte senza segnali, senza errori", c7.segnali == [])
    json.dumps({})


def main():
    for caso in (caso_1, caso_2, caso_3, caso_4, caso_5, caso_6, caso_7, caso_8, caso_9,
                 caso_10):
        caso()
    aperti = sorted(set(buchi))
    print(f"\nBuchi confermati e attesi da correggere dai passi della macchina: {aperti}")
    print(f"{'Tutto bene' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
