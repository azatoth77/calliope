"""Il quarto giro vero della DGX del 10/10 (11:46–11:51, satellite «studio»), a secco
(10/10/2026; docs/aree/voce-e-regole.md, docs/aree/agenti-estensioni.md).

Quattro correzioni puntuali, con i turni veri e i contrari:

A. «Ricominciamo» muto sul satellite. Il journal: «[VOCE] il satellite non ha detto «Va bene,
   ricominciamo da capo.» (turno 0, …)». Il satellite scarta le frasi di un turno che non
   supera l'ultimo fermato (`Riproduttore._scartata`), e la voce di una corsia nuova sta al
   turno 0: la frase detta per prima dopo un riavvio, fuori da una risposta, era scartata. Ora
   `_di_e_aspetta` apre il turno della voce, e lo apre anche la frase presa (`_ascolta`) per
   tutto ciò che si dice prima del modello, e gli annunci. Il satellite finto delle prove
   (`prova_giro3.Remota`, `satellite_finto.py`) scarta come il vero: sul codice di prima la
   prova fallisce.
B. Il cambio di sviluppo faceva partire il lavoro senza analisi: 11:47:41 «Sì» a «Vuoi che
   sospenda Celsius e apra chilometri?» → la frase di sfida (la richiesta era detta senza la
   voce riconosciuta); 11:47:56 la sfida superata → «Ci lavoro in secondo piano». La sfida (la
   conferma della politica, `politica_conferma_unica`) valeva come il «sì» all'analisi mai
   sentita. Ora lo sviluppo si apre all'analisi con «Va bene così, o la cambiamo?»
   (`sviluppo_analisi_prima`) e il lavoro parte al «sì» all'analisi, come un'apertura normale.
C. L'elenco degli sviluppi: 11:49:39 «Ho 4 sviluppi sospesi: …» senza Celsius, il quinto e il
   più recente (i primi quattro in ordine di apertura). Ora tutti nel conto, i più recenti per
   nome, «e altri N» oltre quattro.
D. «C'è Locutti.» → anagrafica_cerca({'testo': '…'}) e la risposta «…»: nel journal sono le
   oscurazioni di un tool riservato (argomenti e risposta), non i valori; la risposta del
   tool si dice. Un argomento di sola punteggiatura vale come vuoto (errore strutturato del
   dialogo dei tool); la risposta di sola punteggiatura dopo un tool riservato ha il ripiego.

    python prove\\prova_giro4.py
"""

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_estensioni as P  # noqa: E402
import prova_giro3 as G3  # noqa: E402
import prova_sviluppo as S  # noqa: E402
from calliope import politica  # noqa: E402
from calliope.tools import dialogo  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


detta = G3.detta
CELSIUS = "Scrivi un programma in Python che converta i gradi Celsius in Fahrenheit."
KM = "Scrivi un programma in Python che converta i chilometri in miglia."
T_KM = "programma in Python che converta i chilometri in miglia"


# ═══════════════════════════ A. frasi fuori turno sul satellite ═══════════════════════════

def _dette(rem, n):
    """Le frasi mandate dopo l'indice `n` che il satellite (finto, come il vero) dice."""
    return [t for k, t in rem.frasi[n:] if t and not rem._scartata(k)]


def prova_fuori_turno():
    print("— A. frasi dette fuori da una risposta, sulla corsia nuova di un satellite")
    rem = G3.Remota()
    c, sp, stt, al_momento = G3.ciclo_satellite(rem)
    verifica("preparazione: la voce di una corsia nuova sta al turno 0, che il satellite "
             "scarta", sp.turno == 0 and rem._scartata(0))
    stt.frasi.append("Calliope, ricominciamo.")
    c.giro()
    verifica("11:46:43: «Calliope, ricominciamo» per primo → la frase arriva in un turno nuovo "
             "e il satellite la dice", _dette(rem, 0) == ["Va bene, ricominciamo da capo."]
             and all(k > 0 for k, _ in rem.frasi)
             and "voce_frase_non_detta" not in (c.rec or {}).get("regole", []),
             f"{rem.frasi} {(c.rec or {}).get('regole')}")
    verifica("…prima della chiusura della conversazione",
             al_momento and al_momento[-1][0] == "nuova"
             and "Va bene, ricominciamo da capo." in al_momento[-1][1], str(al_momento))
    # Il satellite ha sentito il nome (si ferma da sé fino all'ultimo turno ricevuto): la frase
    # successiva fuori risposta va in un turno nuovo
    rem.sente_il_nome()
    n = len(rem.frasi)
    stt.frasi.append("Calliope, ricominciamo.")
    c.giro()
    verifica("dopo il nome sentito dal satellite (ferma senza turno) → di nuovo detta",
             _dette(rem, n) == ["Va bene, ricominciamo da capo."], str(rem.frasi[n:]))
    # «Esci» per primo su una corsia nuova
    rem2 = G3.Remota()
    c2, sp2, stt2, _ = G3.ciclo_satellite(rem2)
    stt2.frasi.append("Calliope, esci.")
    c2.giro()
    verifica("«esci» per primo su una corsia nuova → «A presto!» detto, e si addormenta",
             _dette(rem2, 0) == ["A presto!"] and c2.awake_until == 0.0, str(rem2.frasi))
    # La cortesia per prima («Prego!», frase pronta)
    rem3 = G3.Remota()
    c3, sp3, stt3, _ = G3.ciclo_satellite(rem3)
    c3.awake_until = time.monotonic() + 30
    stt3.frasi.append("Grazie.")
    pronte = []
    sp3.say_cached = lambda testo: (pronte.append((sp3.turno, testo)),
                                    rem3.invia(sp3.turno, testo, b"", 16000))
    c3.giro()
    verifica("la cortesia per prima su una corsia nuova → la frase in un turno che il "
             "satellite dice", pronte and all(k > 0 for k, _ in pronte)
             and _dette(rem3, 0), f"{pronte} {(c3.rec or {}).get('regole')}")
    # Un annuncio (timer scaduto) su una corsia nuova, prima di ogni turno
    rem4 = G3.Remota()
    c4, sp4, stt4, _ = G3.ciclo_satellite(rem4)
    c4.annunci.agenda.put({"kind": "timer", "label": "della pasta", "due": time.time(),
                           "owner_name": ""})
    c4.giro()
    verifica("un annuncio per primo su una corsia nuova → detto", _dette(rem4, 0) == [
        "è scaduto il timer della pasta."], str(rem4.frasi))
    # Contrario: il satellite che davvero non la dice → la regola resta
    rem5 = G3.Remota(dice=False)
    c5, _, stt5, _ = G3.ciclo_satellite(rem5)
    stt5.frasi.append("Calliope, ricominciamo.")
    c5.giro()
    verifica("contrario: il satellite che non la dice → `voce_frase_non_detta`",
             "voce_frase_non_detta" in (c5.rec or {}).get("regole", []), str(c5.rec))


def prova_satellite_finto():
    print("— A2. il satellite finto a livello di protocollo scarta come il vero")
    from satellite_finto import SatelliteFinto
    s = SatelliteFinto("ws://127.0.0.1:1", "x")
    sc = []

    class WS:
        def __init__(self, msg):
            self.msg = msg

        def __iter__(self):
            return iter(self.msg)

        def send(self, m):
            sc.append(m)
    from calliope.satellite import protocollo as Pr
    s.ws = WS([Pr.testo(tipo="frase", turno=0, id=1, testo="Va bene, ricominciamo da capo.",
                        rate=16000, byte=0),
               Pr.testo(tipo="frase", turno=1, id=2, testo="Ciao.", rate=16000, byte=0),
               Pr.testo(tipo="ferma", turno=1),
               Pr.testo(tipo="frase", turno=1, id=3, testo="Scartata.", rate=16000, byte=0),
               Pr.testo(tipo="frase", turno=2, id=4, testo="Detta.", rate=16000, byte=0)])
    s._leggi()
    verifica("turno 0 scartato, il turno fermato scartato, gli altri detti",
             [t for _, t in s.frasi] == ["Ciao.", "Detta."]
             and [t for _, t in s.scartate] == ["Va bene, ricominciamo da capo.", "Scartata."],
             f"{s.frasi} {s.scartate}")


# ═══════════════════════════ B. il cambio si apre all'analisi ═══════════════════════════

def _cambio_con_sfida(tmp, iso):
    """Celsius all'analisi, la richiesta dei chilometri detta con una frase breve (11:47:14),
    il «sì» (11:47:41) → sospeso Celsius, frase di sfida."""
    cfg, reg, ctx, est, svc, r = G3.apri(
        tmp, iso, compito=CELSIUS,
        detto="Scrivimi un programma in Python che converte i gradi Celsius in Fahrenheit.")
    cel = svc.sviluppi.corrente("u1")
    G3.turno(reg, ctx, "Scrivimi un programma in Python che converte i chilometri in miglia.",
             "sviluppo_apri", {"tipo": "programma", "compito": KM}, 3, come="breve")
    r = G3.turno(reg, ctx, "Sì.", "sviluppo_passo", {"azione": "sospendi"}, 4, come="breve",
                 sospeso="sviluppo_passo")
    return cfg, reg, ctx, svc, cel, r


def _supera_sfida(reg, ctx, n):
    """La frase di sfida ripetuta: Brain richiama il tool proposto con i suoi argomenti, la
    politica la sa (Turno.sfida) e la dà per accettata (`politica_conferma_unica`)."""
    s = ctx.speaker_ctx.sfida
    ctx.regole = []
    ctx.speaker_ctx.sfida, ctx.speaker_ctx.sfida_superata = None, True
    ctx.user_text = "girasole valigia pennello cinquantasei"
    ctx.tool_in_sospeso = s.tool
    ctx.politica = politica.Turno(testo=ctx.user_text, in_sospeso=s.tool,
                                  args_sospeso=dict(s.argomenti), sfida=True)
    try:
        return P.chiama(reg, ctx, s.tool, dict(s.argomenti), turno=n)
    finally:
        ctx.speaker_ctx.sfida_superata = False
        ctx.tool_in_sospeso = ctx.politica = None


def prova_cambio(tmp, iso):
    print("— B. il cambio di sviluppo con la sfida si apre all'analisi")
    cfg, reg, ctx, svc, cel, r = _cambio_con_sfida(tmp / "a", iso)
    verifica("11:47:41: Celsius sospeso e la frase di sfida (la richiesta era senza la voce)",
             cel.stato == "sospesa" and "sfida_voce" in ctx.regole
             and ctx.speaker_ctx.sfida is not None and not svc.attivi(), f"{ctx.regole}")
    r = _supera_sfida(reg, ctx, 5)
    km = svc.sviluppi.corrente("u1")
    verifica("11:47:56: sfida superata → lo sviluppo dei chilometri all'analisi con «Va bene "
             "così, o la cambiamo?», nessun lavoro partito",
             km is not None and km.titolo == T_KM and km.fase == "analisi" and km.proposto
             and km.lavoro is None and not svc.attivi() and "Va bene così" in detta(r)
             and "Ci lavoro" not in detta(r) and "sviluppo_fase" not in ctx.regole
             and "sviluppo_analisi_prima" in ctx.regole
             and "politica_conferma_unica" in ctx.regole, f"{ctx.regole} {detta(r)}")
    verifica("…la proposta è in sospeso per il «sì» all'analisi",
             (r.get("in_sospeso") or {}).get("argomenti", {}).get("proposta") == km.proposto,
             str(r.get("in_sospeso")))
    r = G3.turno(reg, ctx, "Sì, va bene.", "sviluppo_apri", {"proposta": km.proposto}, 6,
                 come="breve", sospeso="sviluppo_apri")
    verifica("…e il «sì» all'analisi avvia il lavoro dei chilometri",
             "Ci lavoro" in detta(r) and km.lavoro and any(
                 "chilometri" in lv.compito for lv in svc.attivi()), f"{ctx.regole} {detta(r)}")
    # Allineato con l'apertura normale: una richiesta senza la voce → sfida → analisi
    cfg, reg, ctx, est, svc = S.ambiente(tmp / "b", iso)
    ctx.speaker_ctx = P.speaker(come="breve")
    ctx.user_text = "Scrivimi un programma in Python che converte i chilometri in miglia."
    r = P.chiama(reg, ctx, "sviluppo_apri", {"tipo": "programma", "compito": KM}, turno=1)
    verifica("apertura normale con una frase breve → la sfida", "ripeti" in detta(r).lower()
             and ctx.speaker_ctx.sfida is not None, detta(r))
    r = _supera_sfida(reg, ctx, 2)
    km = svc.sviluppi.corrente("u1")
    verifica("…superata → all'analisi, nessun lavoro (prima partiva subito anche qui)",
             km is not None and km.fase == "analisi" and not svc.attivi()
             and "Va bene così" in detta(r), f"{ctx.regole} {detta(r)}")
    # Contrario: apertura con la voce riconosciuta, com'era
    cfg, reg, ctx, est, svc, r = G3.apri(tmp / "c", iso, compito=KM,
                                         detto="Scrivimi un programma che converte i km.")
    verifica("contrario: con la voce riconosciuta l'analisi come sempre, nessuna sfida",
             "Va bene così" in detta(r) and ctx.speaker_ctx.sfida is None
             and not svc.attivi(), detta(r))


# ═══════════════════════════ C. l'elenco degli sviluppi ═══════════════════════════

def prova_elenco(tmp, iso):
    print("— C. «che sviluppi ho aperto?»: tutti nel conto, i più recenti per nome")
    from calliope.sviluppo import elenco
    cfg, reg, ctx, est, svc = S.ambiente(tmp / "a", iso)
    svs = svc.sviluppi
    titoli = ["programma in Python che sommi due numeri",
              "programma in Python che moltiplichi due numeri",
              "programma in Python che conti le vocali",
              "programma in Python che moltiplica due numeri",
              "programma in Python che converta i gradi Celsius in Fahrenheit"]
    for i, t in enumerate(titoli):
        sv = svs.apri("u1", "Dario", "programma", t, titolo=t)
        svs.sospendi(sv) if hasattr(svs, "sospendi") else svs._cambia_stato(sv, "sospesa", "x")
        sv.ultimo = 1000.0 + i
    verifica("preparazione: cinque sospesi, Celsius il più recente",
             len(svs.sospesi("u1")) == 5 and svs.sospesi("u1")[0].titolo == titoli[-1])
    r = G3.turno(reg, ctx, "Calliope, che sviluppi ho aperto?", "sviluppo_passo",
                 {"azione": "stato"}, 2)
    f = detta(r)
    verifica("11:49:39: «Ho 5 sviluppi sospesi», Celsius per primo, «e un altro»",
             f.startswith("Ho 5 sviluppi sospesi: «programma in Python che converta i gradi "
                          "Celsius in Fahrenheit»") and f.count("«") == 4
             and "e un altro. Dimmi quale riprendere." in f, f)
    promem = svs.promemoria_giorno("u1") or ""
    verifica("il promemoria del giorno: lo stesso elenco", "hai 5 sviluppi sospesi" in promem
             and "Celsius" in promem and "e un altro" in promem, promem)
    dati = svs.dati_sospesi("u1") or ""
    verifica("i dati del turno per il modello: tutti e cinque (fino a otto)",
             all(t in dati for t in titoli), dati)
    verifica("elenco: oltre il tetto «e altri N»",
             elenco(list("abcdef"), str, 4) == "a, b, c, d e altri 2"
             and elenco(list("ab"), str, 4) == "a e b" and elenco([], str) == "")
    # Contrario: uno solo
    cfg, reg, ctx, est, svc = S.ambiente(tmp / "b", iso)
    sv = svc.sviluppi.apri("u1", "Dario", "programma", titoli[0], titolo=titoli[0])
    svc.sviluppi._cambia_stato(sv, "sospesa", "x")
    r = G3.turno(reg, ctx, "Che sviluppi ho?", "sviluppo_passo", {"azione": "stato"}, 2)
    verifica("contrario: uno solo → «Ho uno sviluppo sospeso: …»",
             detta(r) == f"Ho uno sviluppo sospeso: «{titoli[0]}» (all'analisi). Dimmi quale "
             "riprendere.", detta(r))


# ═══════════════════════════ D. «…» e il tool riservato ═══════════════════════════

def prova_punteggiatura_argomento():
    print("— D1. un argomento di sola punteggiatura vale come vuoto")
    params = {"type": "object", "properties": {"testo": {"type": "string"}},
              "required": ["testo"]}

    def cerca(ctx, testo):
        return {}
    for v in ("…", "...", " . ", "?", "«»", "-"):
        _, _, err = dialogo.controlla("anagrafica_cerca", params, {"testo": v}, cerca)
        verifica(f"«{v}» → errore strutturato, campo mancante",
                 err is not None and err.get("campo") == "testo", str(err))
    for v in ("Locutti", "C'è Locutti", "3", "Rossi S.r.l.", "è"):
        _, _, err = dialogo.controlla("anagrafica_cerca", params, {"testo": v}, cerca)
        verifica(f"contrario: «{v}» è un valore", err is None, str(err))


def prova_riservato_brain():
    print("— D2. Brain: tool riservato, la risposta si dice; «…» non arriva al tool")
    from prove.prova_politica import chiama, prepara, testo, turno
    from calliope.tools.spec import ToolSpec
    b, _, _ = prepara()
    cercati = []

    def cerca(ctx, testo=""):
        cercati.append(testo)
        return {"ok": False, "conferma": f"In rubrica non trovo «{testo}».",
                "risposta_finale": f"In rubrica non trovo «{testo}»."}
    b.tools.register(ToolSpec(
        "anagrafica_cerca", "Cerca un contatto nella rubrica dell'ufficio.",
        {"type": "object", "properties": {"testo": {"type": "string"}}, "required": ["testo"]},
        cerca, levels=frozenset({"familiare", "amministra"}), riservato=True))
    r = turno(b, "C'è Locutti.", chiama("anagrafica_cerca", {"testo": "Locutti"}))
    verifica("11:49:12: la frase del tool si dice (nel journal «…» è l'oscuramento)",
             r == "In rubrica non trovo «Locutti»." and cercati == ["Locutti"]
             and b.last_private, f"{r!r} {cercati}")
    r = turno(b, "C'è Locutti.", chiama("anagrafica_cerca", {"testo": "…"}),
              chiama("anagrafica_cerca", {"testo": "Locutti"}))
    verifica("«…» come testo → errore strutturato al modello, il tool non parte; il modello "
             "richiama con il nome", cercati == ["Locutti", "Locutti"]
             and "tool_argomenti_mancanti" in b.rules_fired()
             and r == "In rubrica non trovo «Locutti».", f"{r!r} {b.rules_fired()} {cercati}")
    r = turno(b, "C'è Locutti.", chiama("anagrafica_cerca", {"testo": "…"}), testo("…"),
              testo("…"), testo("…"), testo("…"))
    verifica("…e se poi risponde solo «…»: una frase vera, non il silenzio",
             any(ch.isalpha() for ch in r) and len(cercati) == 2, f"{r!r} {b.rules_fired()}")


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-giro4-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    t0 = time.perf_counter()
    prova_fuori_turno()
    prova_satellite_finto()
    prova_cambio(tmp0 / "cambio", iso)
    prova_elenco(tmp0 / "elenco", iso)
    prova_punteggiatura_argomento()
    prova_riservato_brain()
    print(f"\n[{time.perf_counter() - t0:.1f} s]")
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
