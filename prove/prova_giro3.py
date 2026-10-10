"""Il terzo giro vero della DGX del 10/10 (10:37–10:44, satellite «studio»), a secco
(10/10/2026; docs/aree/agenti-estensioni.md, docs/aree/voce-e-regole.md).

Cinque correzioni, con i turni veri e i contrari:

A. Un altro compito non è una modifica dell'analisi. 10:39:47 e 10:40:08: con «…converte i gradi
   Celsius in Fahrenheit» all'analisi, «…converte i chilometri in miglia» → sviluppo_passo
   analisi con cambia = il compito nuovo → «Ho capito così: …Celsius… Con questa modifica:
   …chilometri…». Ora la domanda con i due titoli (`sviluppo_analisi_altro`) e il «sì» sospende
   e apre; contrari: le modifiche vere («deve contare anche le righe», «usa una funzione»,
   «aggiungi i decimali»).
B. Una conferma deve contenere una parola riconoscibile. 10:39:07: «CQD» → lo sviluppo chiuso.
   Ora «Non ho capito: lo chiudo?» (`consenso_irriconoscibile`), anche con la conferma breve e
   con proposta_rispondi in ombra; contrari: «sì», «ok», «va bene», «certo», «sì sì», «chiudilo»,
   le storpiature note.
C. Titoli con le parole che distinguono («…converte i gradi Celsius in Fahrenheit», «…converte i
   chilometri in miglia»); i titoli buoni di prima restano uguali.
D. «Chiudi tutti gli sviluppi» (10:43:09, 10:43:26): sviluppo_passo chiudi con quale = «tutti»,
   una domanda sola, al «sì» chiusi tutti e fermato il lavoro dell'agente.
E. «Ricominciamo» sulla corsia di un satellite: la frase detta prima della chiusura della
   conversazione, e il log se il satellite non la dice (`voce_frase_non_detta`).

    python prove\\prova_giro3.py
"""

import os
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_ciclo as C  # noqa: E402
import prova_estensioni as P  # noqa: E402
import prova_sviluppo as S  # noqa: E402
from calliope import corsie, politica, tts  # noqa: E402
from calliope import taratura_voce as tv  # noqa: E402
from calliope.agenti.servizio import titolo_da  # noqa: E402
from calliope.ciclo import Ciclo, Servizi  # noqa: E402
from calliope.config import Config  # noqa: E402
from calliope.cortesia import Cortesia  # noqa: E402
from calliope.risposte import forma_chiusa, senza_parole  # noqa: E402
from calliope.sviluppo import altro_compito_in_cambia  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def detta(r) -> str:
    return str((r or {}).get("risposta_finale") or (r or {}).get("conferma") or "")


CELSIUS = "scrivi un programma in Python che converte i gradi Celsius in Fahrenheit"
KM = "scrivi un programma in Python che converte i chilometri in miglia"
T_CELSIUS = "programma in Python che converte i gradi Celsius in Fahrenheit"
T_KM = "programma in Python che converte i chilometri in miglia"
VOCALI = ("scrivi un programma in Python che conti il numero di vocali in una stringa fornita "
          "dall'utente")


def apri(tmp, iso, compito=CELSIUS,
         detto="Scrivimi un programma in Python che converte i gradi Celsius in Fahrenheit."):
    """Dario chiede un programma con la voce: sviluppo aperto all'analisi, proposta L1."""
    cfg, reg, ctx, est, svc = S.ambiente(tmp, iso)
    ctx.speaker_ctx = P.speaker()
    ctx.user_text = detto
    r = P.chiama(reg, ctx, "sviluppo_apri", {"tipo": "programma", "compito": compito}, turno=1)
    return cfg, reg, ctx, est, svc, r


def turno(reg, ctx, detto, nome, args, n, come="voce", sospeso=None, t=None):
    ctx.regole = []
    ctx.user_text = detto
    ctx.speaker_ctx = P.speaker(come=come)
    ctx.tool_in_sospeso = sospeso
    ctx.politica = t
    try:
        return P.chiama(reg, ctx, nome, args, turno=n)
    finally:
        ctx.tool_in_sospeso = None
        ctx.politica = None


# ═══════════════════════════ A. un altro compito nell'analisi ═══════════════════════════

def prova_cambia_criterio():
    print("— A1. altro_compito_in_cambia: un compito intero che sostituisce il titolo")
    sv = types.SimpleNamespace(titolo=T_CELSIUS, richiesta=CELSIUS, specifica=CELSIUS)
    sv_v = types.SimpleNamespace(titolo="programma in Python che conti il numero di vocali",
                                 richiesta=VOCALI, specifica=VOCALI)
    casi = [
        ("10:39:47: i chilometri al posto dei gradi", KM, sv, True),
        ("un'estensione diversa detta come modifica",
         "crea un'estensione che dica le maree di Genova", sv, True),
        ("«un altro programma che…»", "un altro programma che converte i litri in galloni", sv,
         True),
        ("contrario: «deve contare anche le righe»", "deve contare anche le righe", sv_v, False),
        ("contrario: «usa una funzione»", "usa una funzione", sv_v, False),
        ("contrario: «aggiungi i decimali»", "aggiungi i decimali", sv, False),
        ("contrario: «converte anche i gradi Kelvin» (senza una cosa nuova)",
         "converte anche i gradi Kelvin", sv, False),
        ("contrario: il compito di prima ripetuto con «un programma»",
         "un programma in Python che converte i gradi Celsius in Fahrenheit e viceversa", sv,
         False),
        ("contrario: «il programma deve chiedere i gradi»", "il programma deve chiedere i gradi",
         sv, False),
        ("contrario: vuoto", "", sv, False),
    ]
    for nome, cambia, s, atteso in casi:
        verifica(nome, altro_compito_in_cambia(cambia, s) == atteso, cambia)


def prova_cambia_tool(tmp, iso):
    print("— A2. il giro vero: sviluppo_passo analisi con il compito dei chilometri")
    cfg, reg, ctx, est, svc, r = apri(tmp / "a", iso)
    svs = svc.sviluppi
    cel = svs.corrente("u1")
    verifica("preparazione: Celsius all'analisi con il titolo che distingue, proposta L1",
             cel is not None and cel.titolo == T_CELSIUS and cel.proposto == "L1", cel and
             cel.titolo)
    spec = cel.specifica
    r = turno(reg, ctx, "Scrivimi un programma in Python che converte i chilometri in miglia.",
              "sviluppo_passo", {"azione": "analisi", "cambia": KM}, 3)
    f, sosp = detta(r), r.get("in_sospeso") or {}
    verifica("10:39:47: niente «Con questa modifica», la domanda con i due titoli",
             "Con questa modifica" not in f and f"«{T_CELSIUS}»" in f and f"«{T_KM}»" in f
             and f.endswith(f"Vuoi che sospenda «{T_CELSIUS}» e apra «{T_KM}»?")
             and sosp.get("argomenti") == {"azione": "sospendi"}, f)
    verifica("…regole `sviluppo_analisi_altro` e `sviluppo_altro_bloccato`; specifica e "
             "proposta di Celsius non cambiano, niente lavoro nuovo",
             "sviluppo_analisi_altro" in ctx.regole and "sviluppo_altro_bloccato" in ctx.regole
             and "sviluppo_analisi" not in ctx.regole and cel.specifica == spec
             and cel.proposto == "L1" and not svc.attivi(), f"{ctx.regole}")
    # 10:40:08: lo stesso richiamo, di nuovo la stessa domanda
    r = turno(reg, ctx, "No, non va bene così. Voglio che sospendi quello in Celsius e applichi "
              "lo sviluppo soltanto alla versione chilometri in miglia.", "sviluppo_passo",
              {"azione": "analisi", "cambia": KM}, 4)
    verifica("10:40:08: di nuovo la domanda, la specifica di Celsius resta",
             detta(r).endswith("?") and cel.specifica == spec and "Con questa modifica"
             not in detta(r), detta(r))
    r = turno(reg, ctx, "Sì.", "sviluppo_passo", {"azione": "sospendi"}, 5, come="breve",
              sospeso="sviluppo_passo")
    nuovo = svs.corrente("u1")
    verifica("il «sì»: Celsius sospeso, aperto lo sviluppo dei chilometri con la sua analisi",
             cel.stato == "sospesa" and nuovo is not None and nuovo is not cel
             and nuovo.titolo == T_KM and nuovo.fase == "analisi" and nuovo.proposto
             and "sviluppo_cambio" in ctx.regole and not svc.attivi(),
             f"{ctx.regole} {detta(r)}")
    # Contrari: le modifiche vere restano modifiche
    for i, mod in enumerate(("aggiungi i decimali", "usa una funzione",
                             "deve chiedere i gradi all'utente")):
        cfg, reg, ctx, est, svc, r = apri(tmp / f"m{i}", iso)
        cel = svc.sviluppi.corrente("u1")
        r = turno(reg, ctx, mod, "sviluppo_passo", {"azione": "analisi", "cambia": mod}, 3)
        verifica(f"contrario: «{mod}» è una modifica dell'analisi («Con questa modifica»)",
                 "sviluppo_analisi" in ctx.regole and "sviluppo_analisi_altro" not in ctx.regole
                 and "Con questa modifica" in detta(r) and mod in detta(r)
                 and svc.sviluppi.corrente("u1") is cel, f"{ctx.regole} {detta(r)}")


# ═══════════════════════════ B. una conferma senza parole ═══════════════════════════

def prova_senza_parole():
    print("— B1. senza_parole: sigle, sillabe e rumore; i contrari")
    si = ["CQD", "CQD.", "Mh.", "Ehm…", "TV", "Boh.", "Calliope, CQD.", "Xq"]
    no = ["Sì.", "sì sì", "Ok.", "Va bene.", "Certo.", "Chiudilo.", "Sì, chiudi.", "No.",
          "D'accordo.", "Esatto.", "Yes.", "Okay.", "3", "Chiudi.",
          # le storpiature note hanno il loro percorso (il dato del turno, la corsia veloce)
          "Chiudin.", "Spendilo.", "Annullahi.", "Giudino."]
    for x in si:
        verifica(f"senza parole: «{x}»", senza_parole(x))
    for x in no:
        verifica(f"contrario, ha parole: «{x}»", not senza_parole(x))
    verifica("la corsia veloce non prende «CQD» per un sì", forma_chiusa("CQD") is None)


def _vocali_aperto(svs):
    sv = svs.apri("u1", "Dario", "programma", VOCALI,
                  titolo="programma in Python che conti il numero di parole")
    sv.specifica = VOCALI
    return sv


def prova_cqd_tool(tmp, iso):
    print("— B2. nell'esecutore: il «sì» al tool proposto da «CQD», anche con la conferma breve")
    cfg, reg, ctx, est, svc = S.ambiente(tmp, iso)
    sv = _vocali_aperto(svc.sviluppi)
    r = turno(reg, ctx, "Chiudi lo sviluppo delle parole.", "sviluppo_passo",
              {"azione": "chiudi"}, 2)
    verifica("preparazione: «Lo chiudo?»", detta(r).endswith("Lo chiudo?"), detta(r))
    for come in ("voce", "breve"):
        t = politica.Turno(testo="CQD", in_sospeso="sviluppo_passo",
                           args_sospeso={"azione": "chiudi"}, domanda_sospeso="Lo chiudo?",
                           cosa_sospeso="chiudere lo sviluppo")
        r = turno(reg, ctx, "CQD", "sviluppo_passo", {"azione": "chiudi"}, 3, come=come,
                  sospeso="sviluppo_passo", t=t)
        sosp = r.get("in_sospeso") or {}
        verifica(f"10:39:07 «CQD» ({come}): non chiude, «Non ho capito: lo chiudo?», la proposta "
                 "resta", sv.stato == "aperta" and detta(r) == "Non ho capito: lo chiudo?"
                 and sosp.get("domanda") == "Lo chiudo?" and sosp.get("tool") == "sviluppo_passo"
                 and sosp.get("argomenti") == {"azione": "chiudi"}
                 and "consenso_irriconoscibile" in ctx.regole
                 and "conferma_breve" not in ctx.regole, f"{ctx.regole} {detta(r)}")
    # Scritto da uno schermo: non è una trascrizione
    t = politica.Turno(testo="CQD", in_sospeso="sviluppo_passo", domanda_sospeso="Lo chiudo?")
    ctx.speaker_ctx = P.speaker(come="schermo")
    ctx.politica = t
    verifica("contrario: scritto da uno schermo → non è questo caso",
             politica.consenso_irriconoscibile("sviluppo_passo", {}, ctx) is None)
    t = politica.Turno(testo="CQD", in_sospeso="lavoro_rispondi", domanda_sospeso="Quale?",
                       risposta_dato=True)
    ctx.speaker_ctx, ctx.politica = P.speaker(), t
    verifica("contrario: la domanda che chiede un dato (dell'agente) → non è questo caso",
             politica.consenso_irriconoscibile("lavoro_rispondi", {}, ctx) is None)
    t = politica.Turno(testo="CQD", in_sospeso="casa_comando", domanda_sospeso="La apro?")
    ctx.politica = t
    verifica("contrario: un altro tool (non quello proposto) → non è questo caso",
             politica.consenso_irriconoscibile("sviluppo_passo", {}, ctx) is None)
    ctx.politica = None
    r = turno(reg, ctx, "Sì.", "sviluppo_passo", {"azione": "chiudi"}, 4, come="breve",
              sospeso="sviluppo_passo",
              t=politica.Turno(testo="Sì.", in_sospeso="sviluppo_passo",
                               domanda_sospeso="Lo chiudo?"))
    verifica("…e il «sì» dopo chiude", sv.stato == "chiusa", detta(r))


def prova_cqd_brain(tmp, iso):
    print("— B3. Brain: «CQD» al «Lo chiudo?» e i contrari")
    cfg, reg, ctx, est, svc, b = S.brain(tmp / "cqd", iso)
    sv = _vocali_aperto(svc.sviluppi)
    b.backend.risposte = [S.chiamata("sviluppo_passo", {"azione": "chiudi"})]
    S.risposta(b, "Chiudi lo sviluppo delle parole.")
    b.backend.risposte = [S.chiamata("sviluppo_passo", {"azione": "chiudi"})]
    detto = S.risposta(b, "CQD")
    verifica("10:39:07: il modello chiama chiudi → «Non ho capito: lo chiudo?», niente chiuso, "
             "la proposta resta", sv.stato == "aperta" and detto == "Non ho capito: lo chiudo?"
             and b.has_pending() and "consenso_irriconoscibile" in b.rules_fired(),
             f"{b.last_rules} {detto}")
    b.backend.risposte = [S.chiamata("sviluppo_passo", {"azione": "chiudi"})]
    detto = S.risposta(b, "Sì, chiudi.")
    verifica("…il «sì» dopo chiude", sv.stato == "chiusa", detto)
    # proposta_rispondi in ombra: «si» diventa la chiamata di oggi, che passa dall'esecutore
    cfg, reg, ctx, est, svc, b = S.brain(tmp / "ombra", iso)
    sv = _vocali_aperto(svc.sviluppi)
    b.backend.risposte = [S.chiamata("sviluppo_passo", {"azione": "chiudi"})]
    S.risposta(b, "Chiudi lo sviluppo delle parole.")
    b.backend.risposte = [S.chiamata("proposta_rispondi", {"esito": "si"}),
                          [("text", "Non ho capito.")]]
    detto = S.risposta(b, "CQD")
    verifica("proposta_rispondi(si) su «CQD» non chiude", sv.stato == "aperta"
             and "consenso_irriconoscibile" in b.rules_fired(), f"{b.rules_fired()} {detto}")
    # Contrari: le risposte vere chiudono
    for i, frase in enumerate(("Sì.", "Ok.", "Va bene.", "Certo.", "Sì sì.", "Chiudilo.",
                               "Chiudin.")):
        cfg, reg, ctx, est, svc, b = S.brain(tmp / f"si{i}", iso)
        sv = _vocali_aperto(svc.sviluppi)
        b.backend.risposte = [S.chiamata("sviluppo_passo", {"azione": "chiudi"})]
        S.risposta(b, "Chiudi lo sviluppo delle parole.")
        b.backend.risposte = [S.chiamata("sviluppo_passo", {"azione": "chiudi"})]
        detto = S.risposta(b, frase)
        verifica(f"contrario: «{frase}» chiude", sv.stato == "chiusa"
                 and "consenso_irriconoscibile" not in b.rules_fired(),
                 f"{b.rules_fired()} {detto}")


# ═══════════════════════════ C. titoli ═══════════════════════════

def prova_titoli():
    print("— C. titoli con le parole che distinguono")
    casi = [
        (CELSIUS, T_CELSIUS), (KM, T_KM),
        ("Scrivi un programma in Python che converte le temperature da Celsius a Fahrenheit",
         "programma in Python che converte le temperature da Celsius a Fahrenheit"),
        ("Scrivi un programma che converte i file CSV in JSON",
         "programma che converte i file CSV in JSON"),
        # contrari: i titoli buoni restano uguali
        (VOCALI, "programma in Python che conti il numero di vocali"),
        ("scrivi un programma in Python che conti il numero di parole in un testo",
         "programma in Python che conti il numero di parole"),
        ("Scrivi un programma in Python che calcoli la somma di tutti i numeri",
         "programma in Python che calcoli la somma di tutti i numeri"),
        ("Scrivi un programma in Python che sommi due numeri inseriti dall'utente e ne stampi "
         "il risultato.", "programma in Python che sommi due numeri"),
        ("Scrivi un programma in Python che moltiplica due numeri.",
         "programma in Python che moltiplica due numeri"),
        ("Scrivi uno script che rinomina le foto per data", "script che rinomina le foto per data"),
        ("Crea un'estensione che dica il meteo di una città qualunque",
         "estensione che dica il meteo"),
        ("Scrivi un programma che conta le vocali", "programma che conta le vocali"),
    ]
    for compito, atteso in casi:
        t = titolo_da(compito)
        verifica(f"«{compito[:60]}» → «{atteso}»", t == atteso, t)
    verifica("i due programmi del giro hanno titoli diversi, con le unità",
             titolo_da(CELSIUS) != titolo_da(KM) and "Fahrenheit" in titolo_da(CELSIUS)
             and "miglia" in titolo_da(KM))
    lungo = ("Scrivi un programma in Python che converte i gradi Celsius in Fahrenheit in Kelvin "
             "in Rankine in Réaumur in Delisle in Newton")
    verifica("tetto di lunghezza per la voce (12 parole)", len(titolo_da(lungo).split()) <= 12,
             titolo_da(lungo))


# ═══════════════════════════ D. chiudi tutti ═══════════════════════════

def _due_sviluppi(svs, svc):
    """Lo sviluppo dei chilometri aperto con l'agente al lavoro, quello di Celsius sospeso."""
    cel = svs.apri("u1", "Dario", "programma", CELSIUS, titolo=T_CELSIUS)
    svs.sospendi(cel)
    km = svs.apri("u1", "Dario", "programma", KM, titolo=T_KM)
    svs.passa(km, "sviluppo")
    km.lavoro = "L9"
    annullati = []
    svs.lavoro_attivo = lambda s: s is km and km.lavoro is not None and km.stato != "chiusa"
    svc.annulla = lambda chi, tutti_di_tutti=False, quale=None: (annullati.append(quale)
                                                                  or {"ok": True})
    return cel, km, annullati


def prova_tutti_tool(tmp, iso):
    print("— D1. sviluppo_passo chiudi, quale = tutti")
    cfg, reg, ctx, est, svc = S.ambiente(tmp / "a", iso)
    cel, km, annullati = _due_sviluppi(svc.sviluppi, svc)
    r = turno(reg, ctx, "Calliope ferma il lavoro e chiudi tutti gli sviluppi.", "sviluppo_passo",
              {"azione": "chiudi", "quale": "tutti"}, 2)
    f, sosp = detta(r), r.get("in_sospeso") or {}
    verifica("10:43:09: una domanda sola con i due titoli e il lavoro che si ferma; niente "
             "chiuso", f.endswith(f"Chiudo «{T_KM}» e «{T_CELSIUS}»?")
             and "l'agente sta lavorando" in f and cel.stato == "sospesa" and km.stato == "aperta"
             and sosp.get("argomenti") == {"azione": "chiudi", "quale": "tutti"}
             and "sviluppo_chiudi_conferma" in ctx.regole and not annullati, f)
    r = turno(reg, ctx, "Chiudili.", "sviluppo_passo", {"azione": "chiudi", "quale": "tutti"}, 3)
    verifica("contrario: richiamato senza il «sì» alla domanda → di nuovo la domanda",
             cel.stato == "sospesa" and km.stato == "aperta" and detta(r).endswith("?"),
             detta(r))
    r = turno(reg, ctx, "Sì.", "sviluppo_passo", {"azione": "chiudi"}, 4, come="breve",
              sospeso="sviluppo_passo")
    verifica("il «sì» (chiudi anche senza quale): chiusi tutti e due, lavoro fermato",
             cel.stato == "chiusa" and km.stato == "chiusa" and annullati == ["L9"]
             and "sviluppo_chiusi_tutti" in ctx.regole and "ho fermato il lavoro" in detta(r),
             f"{ctx.regole} {detta(r)}")
    # Contrario: uno solo → la conferma di sempre
    cfg, reg, ctx, est, svc = S.ambiente(tmp / "b", iso)
    sv = svc.sviluppi.apri("u1", "Dario", "programma", KM, titolo=T_KM)
    r = turno(reg, ctx, "Chiudi tutti gli sviluppi.", "sviluppo_passo",
              {"azione": "chiudi", "quale": "tutti"}, 2)
    verifica("contrario: uno sviluppo solo → «Lo chiudo?» di sempre", detta(r).endswith(
        "Lo chiudo?") and sv.stato == "aperta", detta(r))
    # Contrario: chiudi senza «tutti» chiude solo quello aperto
    cfg, reg, ctx, est, svc = S.ambiente(tmp / "c", iso)
    cel, km, annullati = _due_sviluppi(svc.sviluppi, svc)
    km.lavoro = None
    turno(reg, ctx, "Chiudi lo sviluppo.", "sviluppo_passo", {"azione": "chiudi"}, 2)
    turno(reg, ctx, "Sì.", "sviluppo_passo", {"azione": "chiudi"}, 3, come="breve",
          sospeso="sviluppo_passo")
    verifica("contrario: «chiudi» senza «tutti» chiude solo quello aperto",
             km.stato == "chiusa" and cel.stato == "sospesa")


def prova_tutti_brain(tmp, iso):
    print("— D2. Brain: «ferma il lavoro e chiudi tutti gli sviluppi»")
    cfg, reg, ctx, est, svc, b = S.brain(tmp, iso)
    cel, km, annullati = _due_sviluppi(svc.sviluppi, svc)
    b.backend.risposte = [S.chiamata("sviluppo_passo", {"azione": "chiudi", "quale": "tutti"})]
    detto = S.risposta(b, "Calliope ferma il lavoro e chiudi tutti gli sviluppi.")
    verifica("una chiamata sola: la domanda in fondo, registrata come proposta",
             detto.endswith("?") and b.has_pending() and b.pending.get("tool") == "sviluppo_passo"
             and km.stato == "aperta", detto)
    b.backend.risposte = [S.chiamata("sviluppo_passo", {"azione": "chiudi", "quale": "tutti"})]
    detto = S.risposta(b, "Sì.")
    verifica("…il «sì» chiude tutti e ferma il lavoro", cel.stato == "chiusa"
             and km.stato == "chiusa" and annullati == ["L9"], f"{b.last_rules} {detto}")


# ═══════════════════════════ E. «ricominciamo» sul satellite ═══════════════════════════

class Remota:
    """L'uscita di un satellite finto: riceve le frasi e a fine turno dice quali ha detto.
    Come il satellite vero (dal 10/10, quarto giro) non dice le frasi di un turno che non
    supera l'ultimo fermato (`Riproduttore._scartata`, la stessa funzione): al turno 0 di una
    corsia nuova, o dopo un «ferma» (il nome sentito sul satellite, `sente_il_nome`)."""

    def __init__(self, dice=True):
        self.frasi, self._in_coda_s, self.dice = [], 0.0, dice
        self.scarta_fino = 0

    def _scartata(self, turno) -> bool:
        from calliope.satellite.client import Riproduttore, _Frase
        vero = types.SimpleNamespace(sessione=1, scarta_fino=self.scarta_fino)
        return Riproduttore._scartata(vero, _Frase(1, turno, 0, "", 16000, 0))

    def invia(self, turno, testo, audio, rate):
        self.frasi.append((turno, testo))

    def fine_turno(self):
        return [t for n, t in self.frasi if not self._scartata(n)] if self.dice else []

    def ferma(self, turno):
        self.scarta_fino = max(self.scarta_fino, int(turno or 0))

    def sente_il_nome(self):
        """Il satellite sente il nome: si ferma da sé e scarta fino all'ultimo turno ricevuto
        (client.py: `self.player.ferma()` senza turno)."""
        self.scarta_fino = max([self.scarta_fino] + [n for n, _ in self.frasi])

    def prima_voce(self, turno):
        return None


def ciclo_satellite(remota):
    cfg = Config()
    cfg.speaker_id_enabled = False
    cfg.barge_in_enabled = False
    cfg.debug_audio_dir = None
    cfg.uscita_controllo = False
    voce = types.SimpleNamespace(config=types.SimpleNamespace(sample_rate=16000))
    base = types.SimpleNamespace(_voices={}, voice=voce, pronuncia=None,
                                 _voices_lock=threading.Lock(), _fillers={})
    sp = tts.Speaker(cfg, uscita=remota, base=base)
    sp._pcm = lambda v, testo: b"\0\0" * 16 * len(testo)
    sp._taratura = tv.Taratura(None)
    stt, chi, cervello, persone = C.Whisper(), C.ChiParla(), C.Cervello(), C.Persone()
    chi.current_speaker, chi.identified_by = "Dario", "voce"
    al_momento = []
    cervello.end_conversation = lambda motivo="fine": al_momento.append(
        (motivo, [x[1] for x in remota.frasi]))
    instr = types.SimpleNamespace(dopo_turno=lambda x: x, inizio_voce=lambda: None,
                                  persona=lambda *a: None, origine=lambda: {},
                                  annuncia_verso=lambda *a, **k: None,
                                  risposta_scritta=lambda *a: None)
    srv = Servizi(cfg, registry=persone, stt=stt, instradamento=instr, cortesia=Cortesia(),
                  turns=types.SimpleNamespace(write=lambda r: None), attiva_minori=lambda: False,
                  biblioteca=object(), enroll_pending=False)
    annunci = types.SimpleNamespace(agenda=__import__("queue").Queue(), documenti=None,
                                    installazioni=None, lavori=None, estensioni=None)
    c = Ciclo(srv, corsie.Corsia("sat:studio", satellite_id="studio"), C.Ascolto(), sp, chi,
              cervello, types.SimpleNamespace(), annunci, None, threading.Event())
    return c, sp, stt, al_momento


def prova_ricominciamo():
    print("— E. «ricominciamo» sulla corsia di un satellite finto")
    rem = Remota()
    c, sp, stt, al_momento = ciclo_satellite(rem)
    stt.frasi.append("Calliope, che ore sono?")
    c.giro()
    stt.frasi.append("Calliope, ricominciamo.")
    n = len(rem.frasi)
    c.giro()
    verifica("la frase va al satellite, PRIMA della chiusura della conversazione (come «A "
             "presto!»)", [x[1] for x in rem.frasi[n:]] == ["Va bene, ricominciamo da capo."]
             and al_momento and al_momento[-1][0] == "nuova"
             and "Va bene, ricominciamo da capo." in al_momento[-1][1]
             and "voce_frase_non_detta" not in (c.rec or {}).get("regole", []),
             f"{rem.frasi} {al_momento}")
    verifica("…e resta in ascolto (finestra aperta)", c.awake_until > time.monotonic())
    # Un'interruzione rimasta accesa non la scarta
    sp._interrupted.set()
    stt.frasi.append("Calliope, ricominciamo.")
    n = len(rem.frasi)
    c.giro()
    verifica("con un'interruzione rimasta accesa la frase si sintetizza e parte lo stesso",
             [x[1] for x in rem.frasi[n:]] == ["Va bene, ricominciamo da capo."], str(rem.frasi))
    # Il satellite non la dice: il log e la regola
    rem2 = Remota(dice=False)
    c2, sp2, stt2, _ = ciclo_satellite(rem2)
    stt2.frasi.append("Calliope, ricominciamo.")
    c2.giro()
    verifica("contrario: il satellite non la dice → regola `voce_frase_non_detta`",
             "voce_frase_non_detta" in (c2.rec or {}).get("regole", []), str(c2.rec))
    # «Esci» com'era
    stt.frasi.append("Esci.")
    n = len(rem.frasi)
    c.giro()
    verifica("contrario: «esci» dice «A presto!» e si addormenta",
             [x[1] for x in rem.frasi[n:]] == ["A presto!"] and c.awake_until == 0.0,
             str(rem.frasi[n:]))


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-giro3-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    t0 = time.perf_counter()
    prova_cambia_criterio()
    prova_cambia_tool(tmp0 / "cambia", iso)
    prova_senza_parole()
    prova_cqd_tool(tmp0 / "cqd", iso)
    prova_cqd_brain(tmp0 / "cqd_brain", iso)
    prova_titoli()
    prova_tutti_tool(tmp0 / "tutti", iso)
    prova_tutti_brain(tmp0 / "tutti_brain", iso)
    prova_ricominciamo()
    print(f"\n[{time.perf_counter() - t0:.1f} s]")
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
