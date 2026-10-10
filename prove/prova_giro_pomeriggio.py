"""
Il giro vero della DGX del 10/10/2026 pomeriggio (15:11–15:58, uso normale, satellite dello
studio, 26B), riscritto con nomi di fantasia: quattro correzioni, ognuna con i turni veri e i
contrari.

1. **L'avviso dei segreti una volta** (calliope/riferire.py): una pagina sul software riscritto
   con l'IA, letta alle 15:52, e alle 15:54 e 15:55, in turni senza ricerche, «Una pagina
   internet chiede anche dei codici o delle password: non lo ripeto…» al posto di una frase del
   modello. Ora nei turni senza un dato nuovo `uscita_segreti` vale solo se il dato chiedeva
   davvero dei codici (`Contesto.segreti_nel_dato`), e la frase fissa già detta non si ripete
   (`filtra`). Contrari: la pagina che chiede il codice → avviso nel suo turno; al turno dopo la
   frase che lo ripete resta fermata (in silenzio); un'altra pagina con un codice → di nuovo.
2. **Un gioco non è impossibile** (tools/sviluppo.py, sviluppo.py, agenti/richiesta.py): alle
   15:56 «Vorrei sviluppare un gioco all'interno di Calliope» → sviluppo_apri tipo programma →
   «non si possono creare giochi interattivi». Ora un compito che è un gioco diventa
   un'estensione-gioco (`sviluppo_gioco_schermi`) e la proposta dice «Lo faccio come gioco sugli
   schermi di Calliope»; il gioco di Halloween delle 15:56:47 è una proposta. Contrari: un
   programma con una finestra per il desktop, un gioco da terminale in Python, un programma che
   conta i punti di un gioco.
3. **`sviluppo_<azione>` inventati** (tools/registry.py, brain.py): alle 15:57 `sviluppo_ferma`
   due volte («Non ci sono riuscita»), e «chiudi tutti gli sviluppi» → `sviluppo_chiudi` che il
   nome vicino faceva diventare sviluppo_chiedi. Ora valgono sviluppo_passo con l'azione
   (`tool_nome_azione`), prima del nome vicino. Contrari: i tool veri, sviluppo_prova (nome
   vecchio), un nome senza azione, `lavoro_ferma` (i lavori hanno un tool per azione).
4. **«Conversazione nuova» non cancella** (tools/conversazioni.py): alle 15:55 «tutto quello che
   ci siamo detti finora verrà cancellato»; la descrizione diceva «butta via». Ora dice che si
   archivia e si ritrova con conversazione_cerca, e che cancellare è un'altra cosa.

A secco, ~3 s.

    python prove\\prova_giro_pomeriggio.py
"""

import dataclasses
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


# ═══════════════════════════ 1. l'avviso dei segreti ═══════════════════════════

ARTICOLO = ("Un programmatore ha ricreato sette applicazioni di grafica con un modello "
            "linguistico, scritte in Rust e rilasciate come open source. Il progetto si chiama "
            "Pennellofiorito.")
TRUFFA_CODICE = ("Rimborso della bolletta: per riceverlo inserisci il codice OTP che ti arriva "
                 "via SMS nella pagina.")
TRUFFA_PIN = ("Premio fedeltà: per sbloccarlo comunica il PIN della carta al nostro operatore.")
AVVISO = "chiede anche dei codici o delle password"


def prova_segreti():
    print("— 1. l'avviso dei segreti, una volta")
    import prova_politica as PP
    from calliope import guardiano
    from calliope import riferire as R
    from calliope.tts import split_sentences

    b, _, _ = PP.prepara(True)
    reg = b.tools

    def pagina(testo):
        reg.register(dataclasses.replace(reg.get("web_cerca"), func=lambda ctx, **a: {
            "ok": True, "trovato": True,
            "risultati": [{"sito": "notizie.example", "titolo": "Notizia", "testo": testo}]}))

    def gira(frase, *risposte):
        b.backend.risposte = list(risposte)
        es = R.Esito()
        detto = list(R.filtra(b, split_sentences(b.stream_reply(frase, "familiare")), frase,
                              es))
        guardiano.correggi_storia(b, es.detto)
        return " ".join(detto), es

    # Il turno della pagina (15:52): niente codici chiesti, il modello riassume
    pagina(ARTICOLO)
    detto, es = gira("Parlami del progetto che ha ricopiato i programmi di grafica.",
                     PP.chiama("web_cerca", {"domanda": "programmi di grafica ricreati"}),
                     PP.testo("Si chiama Pennellofiorito: sette applicazioni riscritte in Rust "
                              "con un modello linguistico."))
    verifica("turno della pagina: niente fermato", not es.fermate, str(es.fermate))
    # 15:54: nessuna ricerca, il modello parla di codice e token (le frasi probabili)
    frase_vera = ("Anch'io posso scrivere codice, ma il limite è il numero di token che posso "
                  "leggere.")
    detto, es = gira("Quindi anche tu puoi ottenere un risultato simile.",
                     PP.testo("È un'osservazione molto acuta. " + frase_vera + " Il potenziale "
                              "di collaborazione è enorme."))
    verifica("15:54, senza un dato nuovo: la frase sui token passa, niente avviso",
             AVVISO not in detto and "token" in detto and not es.fermate, detto)
    detto, es = gira("Se ti dicessi che vorrei creare un piccolo gioco, cosa mi dici?",
                     PP.testo("Posso aiutarti in due modi. Se vuoi qualcosa di immediato, posso "
                              "scrivere uno script e darti il codice. Oppure un'estensione."))
    verifica("15:55, senza un dato nuovo: «darti il codice» passa, niente avviso",
             AVVISO not in detto and not es.fermate, detto)
    # La stessa frase nel turno della pagina resta fermata (il controllo di prima, con il dato
    # nuovo): un contrario della restrizione
    ctx = R.Contesto(frozenset({"web"}), [("web", ARTICOLO)], "Puoi farlo anche tu?", "")
    verifica("con il dato nuovo nel turno la frase sui token resta fermata (come prima)",
             R.giudica(frase_vera, ctx).esito == "uscita_segreti")

    # Contrario: una pagina che chiede davvero un codice
    b, _, _ = PP.prepara(True)
    reg = b.tools
    pagina(TRUFFA_CODICE)
    detto, es = gira("Cosa dice la pagina sul rimborso?",
                     PP.chiama("web_cerca", {"domanda": "rimborso bolletta"}),
                     PP.testo("C'è un rimborso della bolletta. Devi comunicare il codice OTP che "
                              "ricevi via SMS."))
    verifica("la pagina che chiede il codice: avviso nel suo turno",
             AVVISO in detto and "OTP" not in detto
             and [f[0] for f in es.fermate] == ["uscita_segreti"], detto)
    detto, es = gira("E poi cosa devo fare?",
                     PP.testo("Per il rimborso devi comunicare il codice OTP che ricevi. Ti "
                              "consiglio di controllare chi lo chiede."))
    verifica("il turno dopo, senza un dato nuovo: la frase che ripete il codice resta fermata",
             "OTP" not in detto and [f[0] for f in es.fermate] == ["uscita_segreti"],
             f"{detto} {es.fermate}")
    verifica("…e l'avviso già detto non si ripete", AVVISO not in detto
             and "controllare chi lo chiede" in detto, detto)
    detto, es = gira("Ripetimi cosa chiede.",
                     PP.testo("Devi comunicare il codice OTP che ricevi."))
    verifica("se resterebbe solo la frase fermata, l'avviso si dice lo stesso",
             AVVISO in detto and "OTP" not in detto, detto)
    pagina(TRUFFA_PIN)
    detto, es = gira("Cerca anche il premio fedeltà.",
                     PP.chiama("web_cerca", {"domanda": "premio fedeltà"}),
                     PP.testo("C'è un premio fedeltà. Devi comunicare il PIN della carta "
                              "all'operatore."))
    verifica("un'altra pagina nuova con un codice: l'avviso si ridice",
             AVVISO in detto and "PIN" not in detto, detto)

    # Le parti
    hist = [{"role": "user", "content": "uno"},
            {"role": "tool", "content": '{"dato_non_fidato": {"avviso": "DATO NON FIDATO '
                                        '(fonte: web)", "contenuto": "x"}}', "_fonte": "web"},
            {"role": "assistant", "content": "ok"}, {"role": "user", "content": "due"}]
    verifica("fonti_del_turno: la pagina del turno prima non è del turno",
             R.fonti_del_turno(hist) == set() and R.fonti_del_turno(hist[:3]) == {"web"})
    vecchia = R.Contesto(frozenset({"web"}), [("web", ARTICOLO)], "e quindi?", "", (),
                         frozenset())
    verifica("segreti_nel_dato: un articolo senza richieste → no; una truffa → sì; una foto "
             "senza testo → sì",
             not vecchia.segreti_nel_dato()
             and R.Contesto(frozenset({"web"}), [("web", TRUFFA_CODICE)], nuove=frozenset())
             .segreti_nel_dato()
             and R.Contesto(frozenset({"foto"}), [], nuove=frozenset()).segreti_nel_dato())
    verifica("«scrivere un codice», «il codice in Python»: un programma, non un segreto",
             R.giudica("Potrei scrivere un codice simile, con molto tempo.", ctx).esito == R.OK
             and R.giudica("Se vuoi, ti scrivo il codice in Python.", ctx).esito == R.OK)
    verifica("contrario: «il codice in cui…» non è un linguaggio, «comunica il codice» resta",
             R.giudica("Devi comunicare il codice in cui trovi le cifre.", ctx).esito
             == "uscita_segreti")


# ═══════════════════════════ 2. i giochi ═══════════════════════════

HALLOWEEN = ("un piccolo gioco di paura per Halloween: si sceglie una porta, a volte appare un "
             "mostro con una piccola animazione, e se esce un mostro si guadagnano punti")


def prova_giochi(tmp: Path):
    print("— 2. un gioco è un'estensione sugli schermi")
    import prova_sviluppo_v2 as V
    from calliope.agenti import richiesta as ar
    from calliope.tools import sviluppo as ts
    import prova_estensioni as P

    S = ts.gioco_sugli_schermi
    verifica("gioco_sugli_schermi: «un gioco», «un piccolo gioco di paura…», «crea un "
             "minigioco»", S("un gioco") and S(HALLOWEEN) and S("crea un minigioco di memoria"))
    verifica("contrari: un programma con una finestra, un gioco da terminale in Python, i punti "
             "di un gioco di carte",
             not S("un programma con una finestra per il desktop")
             and not S("un gioco da terminale in Python")
             and not S("un programma che conta i punti del gioco di carte")
             and not S("un gioco", "un gioco per Windows con una finestra"))

    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    cfg, reg, ctx, est, svc = V.ambiente(tmp / "gioco", iso)
    ctx.regole = []
    ctx.user_text = "Vorrei sviluppare un gioco all'interno di Calliope."
    out = P.chiama(reg, ctx, "sviluppo_apri", {"compito": "un gioco", "tipo": "programma"},
                   turno=1)
    sv = svc.sviluppi.corrente("u1")
    frase = str(out.get("risposta_finale") or out.get("conferma") or "")
    verifica("15:56: «un gioco» tipo programma → estensione-gioco (sviluppo_gioco_schermi)",
             "sviluppo_gioco_schermi" in ctx.regole and sv is not None and sv.gioco
             and sv.tipo == "estensione", f"{ctx.regole} {out}")
    verifica("la proposta dice «Lo faccio come gioco sugli schermi» e non è un rifiuto",
             "Lo faccio come gioco sugli schermi" in frase and "non posso" not in frase.lower()
             and "Va bene così" in frase, frase)
    lav = svc.offerte["u1"]["lavoro"]
    verifica("il lavoro è un gioco (scheda, gioco puro)", lav.gioco and "GIOCO" in lav.vincoli,
             lav.vincoli)

    cfg, reg, ctx, est, svc = V.ambiente(tmp / "halloween", iso)
    ctx.regole = []
    ctx.user_text = ("Io vorrei che questo gioco fosse un piccolo gioco di paura con dei mostri "
                     "che appaiono, tu scegli una porta, c'è una piccola animazione.")
    out = P.chiama(reg, ctx, "sviluppo_apri", {"compito": HALLOWEEN, "tipo": "programma"},
                   turno=1)
    sv = svc.sviluppi.corrente("u1")
    frase = str(out.get("risposta_finale") or "")
    verifica("15:56:47, il gioco di Halloween → proposta d'analisi di un'estensione-gioco",
             sv is not None and sv.gioco and sv.fase == "analisi"
             and "gioco sugli schermi" in frase and "porta" in frase, frase)

    cfg, reg, ctx, est, svc = V.ambiente(tmp / "finestra", iso)
    ctx.regole = []
    ctx.user_text = "Fammi un programma con una finestra per il desktop."
    P.chiama(reg, ctx, "sviluppo_apri", {"compito": "un programma con una finestra per il "
                                                    "desktop", "tipo": "programma"}, turno=1)
    sv = svc.sviluppi.corrente("u1")
    verifica("contrario: un programma con una finestra per il desktop resta un programma",
             "sviluppo_gioco_schermi" not in ctx.regole
             and (sv is None or (sv.tipo == "programma" and not sv.gioco)), ctx.regole)
    cfg, reg, ctx, est, svc = V.ambiente(tmp / "terminale", iso)
    ctx.regole = []
    ctx.user_text = "Scrivimi un gioco da terminale in Python."
    P.chiama(reg, ctx, "sviluppo_apri", {"compito": "un gioco da terminale in Python",
                                         "tipo": "programma"}, turno=1)
    verifica("contrario: un gioco da terminale in Python resta un programma",
             "sviluppo_gioco_schermi" not in ctx.regole, ctx.regole)

    cap = ar.capacita(cfg, "codice")
    verifica("l'analisi di un lavoro di codice sa che un gioco si fa (ESTENSIONE), e che il "
             "programma con le finestre no",
             "gioco" in cap and "ESTENSIONE" in cap and "finestre per il desktop" in cap)
    verifica("l'analisi che risponde ESTENSIONE → esito estensione (non impossibile)",
             ar.interpreta(json.dumps({"impossibile": "ESTENSIONE", "punti": {}}),
                           "codice").esito == "estensione")
    desc = reg.get("sviluppo_apri").description
    verifica("descrizione di sviluppo_apri: un gioco è un'estensione con gioco=true, sugli "
             "schermi", "gioco=true" in desc and "schermi di Calliope" in desc, desc[:300])


# ═══════════════════════════ 3. sviluppo_<azione> ═══════════════════════════

def prova_nomi(tmp: Path):
    print("— 3. nomi sviluppo_<azione> inventati")
    import prova_sviluppo_v2 as V
    import prova_estensioni as P
    from calliope.tools import registry as R

    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    cfg, reg, ctx, est, svc = V.ambiente(tmp / "nomi", iso)
    verifica("nome_con_azione: ferma, chiudi, stop → ferma, elenco → stato, stato",
             R.nome_con_azione("sviluppo_ferma") == ("sviluppo_passo", {"azione": "ferma"})
             and R.nome_con_azione("sviluppo_chiudi") == ("sviluppo_passo", {"azione": "chiudi"})
             and R.nome_con_azione("sviluppo_stop")[1] == {"azione": "ferma"}
             and R.nome_con_azione("sviluppo_elenco")[1] == {"azione": "stato"}
             and R.nome_con_azione("sviluppo_stato")[1] == {"azione": "stato"})
    verifica("contrari: un nome senza azione, la famiglia dei lavori",
             R.nome_con_azione("sviluppo_xyz") is None
             and R.nome_con_azione("sviluppo_prova") is None
             and R.nome_con_azione("lavoro_ferma") is None
             and R.nome_con_azione("ferma") is None)
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_ferma", {}, turno=1)
    verifica("15:57:35, sviluppo_ferma({}) → sviluppo_passo ferma (tool_nome_azione), non "
             "«tool sconosciuto»",
             "tool_nome_azione" in ctx.regole and "sconosciuto" not in json.dumps(out)
             and "Non c'è nessuno sviluppo aperto" in str(out.get("conferma") or
                                                           out.get("risposta_finale") or ""),
             json.dumps(out, ensure_ascii=False))
    verifica("sviluppo_ferma senza argomenti: niente argomenti mancanti",
             reg.mancanti("sviluppo_ferma", {}) == [], str(reg.mancanti("sviluppo_ferma", {})))
    # Due sviluppi aperti (uno sospeso), poi «chiudi tutti gli sviluppi» → sviluppo_chiudi
    from calliope.tools import estensioni as te
    ctx.turno = 2
    te._estensione_crea(ctx, compito="un'estensione che converte le valute", nome="Valute")
    ctx.regole = []
    ctx.user_text = "Sì, preferisco che tu chiuda tutti gli sviluppi aperti."
    out = P.chiama(reg, ctx, "sviluppo_chiudi", {"quale": "tutti"}, turno=3)
    verifica("15:57:59, sviluppo_chiudi → sviluppo_passo chiudi, non sviluppo_chiedi",
             "tool_nome_azione" in ctx.regole and "tool_nome_corretto" not in ctx.regole
             and "sviluppo_chiedi" not in json.dumps(out), json.dumps(out, ensure_ascii=False))
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_prova", {"dati": "Bergamo"}, turno=4)
    verifica("contrario: sviluppo_prova resta il nome vecchio di sviluppo_collauda",
             "tool_nome_vecchio" in ctx.regole and "tool_nome_azione" not in ctx.regole,
             ctx.regole)
    ctx.regole = []
    out = json.loads(reg.call("sviluppo_xyz", {}, ctx, "amministra"))
    verifica("contrario: sviluppo_xyz → l'errore strutturato di sempre",
             "sconosciuto" in out.get("errore", "") and not ctx.regole, str(out))
    ctx.regole = []
    out = json.loads(reg.call("lavoro_ferma", {}, ctx, "amministra"))
    verifica("contrario: lavoro_ferma non diventa uno sviluppo", "tool_nome_azione"
             not in ctx.regole and "sviluppo" not in json.dumps(out.get("nomi_giusti") or []),
             str(out))
    # Brain: il nome si corregge prima di tutto il resto, prima del nome vicino
    from calliope.brain import Brain
    b = Brain.__new__(Brain)
    b.tools = reg
    regole = []
    b._rule = regole.append
    call = {"name": "sviluppo_chiudi", "arguments": {}}
    b._nome_corretto(call)
    verifica("Brain: sviluppo_chiudi → sviluppo_passo(azione=chiudi), non sviluppo_chiedi",
             call == {"name": "sviluppo_passo", "arguments": {"azione": "chiudi"}}
             and regole == ["tool_nome_azione"], f"{call} {regole}")
    call = {"name": "sviluppo_ferma", "arguments": {"azione": "sospendi"}}
    b._nome_corretto(call)
    verifica("Brain: un'azione valida già negli argomenti resta",
             call["arguments"] == {"azione": "sospendi"}, str(call))
    regole.clear()
    call = {"name": "svilupo_passo", "arguments": {"azione": "stato"}}
    b._nome_corretto(call)
    verifica("contrario: un nome storpiato resta del nome vicino (tool_nome_corretto)",
             call["name"] == "sviluppo_passo" and regole == ["tool_nome_corretto"],
             f"{call} {regole}")
    d_chiedi = reg.get("sviluppo_chiedi").description
    d_passo = reg.get("sviluppo_passo").description
    verifica("descrizioni: sviluppo_chiedi solo per domande (chiudere è sviluppo_passo), "
             "sviluppo_passo dice che l'azione va nell'argomento",
             "chiudere" in d_chiedi and "sviluppo_passo" in d_chiedi
             and "sviluppo_ferma" in d_passo)


# ═══════════════════════════ 4. conversazione nuova ═══════════════════════════

def prova_conversazione_nuova():
    print("— 4. «conversazione nuova» non cancella")
    from calliope.tools.conversazioni import conversazioni_specs
    spec = next(s for s in conversazioni_specs() if s.name == "conversazione_nuova")
    d = spec.description
    verifica("la descrizione dice che si archivia e si ritrova, non che si cancella",
             "NON cancella" in d and "conversazione_cerca" in d and "archivia" in d
             and "Butta via" not in d and "vuota" not in d, d[:300])
    verifica("e che cancellare è un'altra cosa (conversazioni_dimentica, dimentica)",
             "conversazioni_dimentica" in d)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="calliope-giro-pomeriggio-"))
    os.environ.setdefault("DOCKER_FINTO_DIR", str(tmp / "docker"))
    import prova_estensioni as P
    os.environ.setdefault("DOCKER_FINTO_IMMAGINI", P.IMMAGINE)
    os.environ.setdefault("DOCKER_FINTO_MODO", "ok")
    prova_segreti()
    prova_giochi(tmp)
    prova_nomi(tmp)
    prova_conversazione_nuova()
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
