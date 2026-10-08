"""Il giro vero della DGX dell'08/10 sera (16:42–17:13, 26B e qwen3.6), a secco (08/10/2026,
giro 4 della modalità sviluppo; docs/aree/agenti-estensioni.md e sicurezza-politica.md).

Riscritto con nomi di fantasia: due estensioni del meteo, «Meteo città» (disattivata) e «Meteo
città codificata», rinominata dalla persona «Meteocittà». La modifica «aggiungi i giorni di
previsione» è passata dal modello in `modifica` al posto del nome (→ «non ho un'estensione…»,
la domanda «Meteo città o Meteocittà?», poi al «sì» breve la frase di sfida «per creare una
funzione nuova» e, superata, una chiamata senza `modifica` che rifiutava). La versione con
`citta` e `giorni` provata con «Pratofiorito, 5 giorni» tutto in `citta` (tre volte «non
trovato»); l'analisi «Ho capito così: X. Con questa modifica: X.»; «avanti» in analisi che
ripeteva la domanda; la revisione «che ora si chiama «Meteo città»».

1. `modifica` con una descrizione: l'estensione nominata in `nome` o nella frase, una sola;
   contrari (nessuna, due attive); la descrizione del parametro; l'elenco con gli stati;
2. una disattivata non rende ambiguo il titolo di un'attiva («Meteo città» e «Meteocittà»);
   per riattivare, la disattivata;
3. il «sì» breve di chi amministra apre lo sviluppo di un'estensione senza la frase di sfida;
   contrari: un programma, la zona grigia; e la sfida, quando serve, tiene la chiamata intera;
4. il collaudo con più input: `argomenti`, «N giorni» nei dati; contrari; gli input nei dati
   del turno; gli argomenti veri per sviluppo_chiedi e sviluppo_correggi;
5. l'analisi: la modifica uguale alla specifica non si ripete; «avanti» accetta la specifica
   già letta anche a offerta scaduta; contrario: un «sì» breve che non basta ripropone;
6. il titolo dato dalla persona resta nella revisione, nell'approvazione e nei vincoli
   dell'agente; il titolo dell'agente solo sulla scheda.

    python prove\\prova_sviluppo_giro4.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_estensioni as P  # noqa: E402
import prova_sviluppo as S  # noqa: E402
from calliope.estensioni.servizio import _nome, preferenza  # noqa: E402
from calliope.tools import agenti as ta  # noqa: E402
from calliope.tools import estensioni as te  # noqa: E402
from calliope.tools import sviluppo as ts  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def j(x) -> str:
    return json.dumps(x, ensure_ascii=False)[:400]


DESCRIZIONE = "aggiungi la possibilità di scegliere quanti giorni di previsioni vedere"
FRASE = ("Calliope, modifichiamo l'estensione Meteocittà aggiungendo i giorni di meteo di cui "
         "voglio fare le previsioni.")

M_VECCHIA = P.manifesto("meteo_citta", "Meteo città", "Dice il meteo di una città.",
                        input_={"type": "object", "properties": {"citta": {
                            "type": "string", "description": "nome della città"}},
                            "required": ["citta"]})
M_COD = P.manifesto("meteo_codificato", "Meteo città codificata",
                    "Dice il meteo di una città, con il nome codificato.",
                    input_={"type": "object", "properties": {"citta": {
                        "type": "string", "description": "nome della città"}},
                        "required": ["citta"]},
                    permessi={"rete": {"pubblica": True, "host": ["api.open-meteo.com"]}})
# La versione nuova: il manifesto dell'agente con il suo titolo, e i giorni
M_GIORNI = P.manifesto("meteo_codificato", "Meteo città", "Dice il meteo e le previsioni per "
                       "una città.",
                       input_={"type": "object", "properties": {
                           "citta": {"type": "string", "description": "nome della città"},
                           "giorni": {"type": "integer", "description": "quanti giorni di "
                                                                        "previsioni, da 1 a 7"}},
                           "required": ["citta"]},
                       permessi={"rete": {"pubblica": True, "host": ["api.open-meteo.com"]}})
CODICE = '''
def esegui(dati, calliope):
    citta = str(dati.get("citta") or "").strip()
    giorni = int(dati.get("giorni") or 1)
    if "," in citta or "giorni" in citta:
        return {"da_dire": "Non ho trovato " + citta + "."}
    return {"da_dire": "A " + citta + " per " + str(giorni) + " giorni: sole."}
'''


def ambiente(tmp, iso):
    cfg, reg, ctx, est, svc = S.ambiente(tmp, iso)
    P.installa(est, M_VECCHIA, S.CODICE2)
    est.archivio.disattiva("meteo_citta")
    P.installa(est, M_COD, S.CODICE2)
    est.archivio.rinomina("meteo_codificato", "Meteocittà")
    est.aggiorna_tool()
    ctx.registro = reg
    return cfg, reg, ctx, est, svc


# ═══════════════════════════ 1–2. quale estensione si cambia ═══════════════════════════

def prova_modifica(tmp, iso):
    print("— 1. `modifica` con una descrizione al posto del nome")
    cfg, reg, ctx, est, svc = ambiente(tmp / "a", iso)
    ctx.user_text = FRASE
    out = P.chiama(reg, ctx, "sviluppo_apri", {
        "tipo": "estensione", "compito": DESCRIZIONE, "modifica": DESCRIZIONE,
        "nome": "Meteocittà"})
    off = svc.offerte.get("u1")
    lav = off["lavoro"] if off else None
    verifica("il caso della DGX (16:43): «modifica» = cosa cambiare e «nome» = Meteocittà → la "
             "versione nuova di meteo_codificato, con i suoi file",
             lav is not None and lav.estensione == "meteo_codificato"
             and "estensione.py" in lav.file_iniziali
             and "estensione_modifica_dal_nome" in ctx.regole
             and S.detta(out).startswith("Sarà una versione nuova di «Meteocittà»"), j(out))
    verifica("…il lavoro e lo sviluppo si chiamano come l'ha chiamata la persona",
             lav is not None and lav.titolo == "Meteocittà"
             and svc.sviluppi.corrente("u1").titolo == "Meteocittà",
             f"{getattr(lav, 'titolo', '')} / {svc.sviluppi.corrente('u1').titolo}")
    verifica("…e i vincoli dell'agente dicono di tenere il titolo scelto dalla persona",
             lav is not None and "Il titolo «Meteocittà» l'ha scelto la persona" in lav.vincoli,
             getattr(lav, "vincoli", "")[:300])

    cfg, reg, ctx, est, svc = ambiente(tmp / "b", iso)
    ctx.user_text = FRASE
    out = P.chiama(reg, ctx, "sviluppo_apri", {"tipo": "estensione", "compito": DESCRIZIONE,
                                               "modifica": DESCRIZIONE})
    verifica("senza «nome»: l'unica estensione nominata nella frase (Meteocittà, l'attiva)",
             (svc.offerte.get("u1") or {}).get("lavoro") is not None
             and svc.offerte["u1"]["lavoro"].estensione == "meteo_codificato", j(out))

    cfg, reg, ctx, est, svc = ambiente(tmp / "c", iso)
    ctx.user_text = "Calliope, aggiungiamo i giorni di previsione."
    out = P.chiama(reg, ctx, "sviluppo_apri", {"tipo": "estensione", "compito": DESCRIZIONE,
                                               "modifica": DESCRIZIONE})
    verifica("contrario: nessuna estensione nominata → niente lavoro, la scelta al modello con "
             "l'elenco e gli stati",
             out.get("ok") is False and not svc.offerte and not svc.lavori
             and "(meteo_codificato, attiva)" in out.get("cosa_fare", "")
             and "(meteo_citta, disattivata)" in out.get("cosa_fare", "")
             and "il NOME" in out.get("cosa_fare", "")
             and svc.sviluppi.corrente("u1") is None, j(out))
    est.archivio.riattiva("meteo_citta")
    est.archivio.rinomina("meteo_citta", "Meteo per Valfiorita")
    ctx.user_text = "Modifica Meteocittà e Meteo per Valfiorita aggiungendo i giorni."
    out = P.chiama(reg, ctx, "sviluppo_apri", {"tipo": "estensione", "compito": DESCRIZIONE,
                                               "modifica": DESCRIZIONE})
    verifica("contrario: due attive nominate nella frase → la scelta al modello",
             out.get("ok") is False and not svc.offerte, j(out))
    spec = reg.get("sviluppo_apri").parameters["properties"]["modifica"]["description"]
    verifica("la descrizione di `modifica`: solo il NOME, mai cosa cambiare (che va in compito)",
             "NOME" in spec and "MAI cosa cambiare" in spec and "compito" in spec, spec)

    print("— 2. una disattivata non rende ambiguo il titolo di un'attiva")
    cfg, reg, ctx, est, svc = ambiente(tmp / "d", iso)
    a = est.archivio
    verifica("«Meteo città» detto (attaccato o staccato) → l'attiva, «Meteocittà»",
             _nome("Meteo città", a) == "meteo_codificato"
             and _nome("meteocittà", a) == "meteo_codificato", _nome("Meteo città", a))
    verifica("…per riattivarla, la disattivata", _nome("Meteo città", a, preferenza("riattiva"))
             == "meteo_citta")
    verifica("…con il suo nome interno, sempre quella", _nome("meteo_citta", a) == "meteo_citta")
    out = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "riattiva", "nome": "Meteo città"})
    verifica("estensione_gestisci riattiva «Meteo città» → la disattivata torna attiva",
             a.voce("meteo_citta")["stato"] == "attiva", j(out))
    br = te.elenco_breve(est)
    verifica("l'elenco per il modello ha gli stati",
             "«Meteocittà» (meteo_codificato, attiva)" in br, br)


# ═══════════════════════════ 3. il «sì» breve e la sfida ═══════════════════════════

def prova_breve(tmp, iso):
    print("— 3. il «sì» breve di chi amministra apre lo sviluppo, senza la sfida")
    cfg, reg, ctx, est, svc = ambiente(tmp / "a", iso)
    sc = ctx.speaker_ctx
    sc.identified_by, sc.conferma_breve = "breve", True
    ctx.user_text = "Sì, te lo confermo."
    out = P.chiama(reg, ctx, "sviluppo_apri", {
        "tipo": "estensione", "compito": DESCRIZIONE, "modifica": "Meteocittà"})
    verifica("il caso della DGX (16:45): niente frase di sfida, la proposta della versione nuova",
             svc.offerte.get("u1") is not None and sc.sfida is None
             and "sviluppo_apri_breve" in ctx.regole and "sfida_voce" not in ctx.regole, j(out))
    prof, why = ta._permesso(ctx, "codice", rigido=True, args={"tipo": "programma",
                                                              "compito": "rinomina le foto"})
    verifica("contrario: un programma nuovo col «sì» breve → la frase di sfida (di sempre)",
             prof is None and isinstance(why, dict) and "ripeti" in S.detta(why).lower(), j(why))

    cfg, reg, ctx, est, svc = ambiente(tmp / "b", iso)
    sc = ctx.speaker_ctx
    sc.identified_by, sc.conferma_breve = "breve", False
    ctx.user_text = "Sì."
    out = P.chiama(reg, ctx, "sviluppo_apri", {
        "tipo": "estensione", "compito": DESCRIZIONE, "modifica": DESCRIZIONE,
        "nome": "Meteocittà"})
    arg = getattr(sc.sfida, "argomenti", None) or {}
    verifica("contrario: un «sì» breve che non basta → la frase di sfida, con la chiamata intera "
             "(tipo e l'estensione da cambiare): rifatta dopo la sfida è la stessa",
             not svc.offerte and sc.sfida is not None and arg.get("tipo") == "estensione"
             and arg.get("modifica") == "meteo_codificato" and arg.get("compito") == DESCRIZIONE,
             f"{j(out)} {arg}")
    cfg, reg, ctx, est, svc = ambiente(tmp / "c", iso)
    sc = ctx.speaker_ctx
    sc.identified_by, sc.conferma_breve = "breve", False
    ctx.user_text = "Sì."
    out = P.chiama(reg, ctx, "sviluppo_apri", {"tipo": "estensione", "compito": DESCRIZIONE,
                                               "modifica": "aggiungi i giorni"})
    verifica("una chiamata che rifiuterebbe («non ho un'estensione…») non chiede la sfida prima",
             sc.sfida is None and out.get("ok") is False and "da cambiare" in out.get("errore", ""),
             j(out))


# ═══════════════════════════ 4. collaudo con più input ═══════════════════════════

def al_collaudo(ctx, est, svc):
    ctx.user_text = FRASE
    P.chiama(ctx.registro, ctx, "sviluppo_apri", {
        "tipo": "estensione", "compito": DESCRIZIONE, "modifica": "Meteocittà"}, turno=1)
    lav = svc.offerte["u1"]["lavoro"]
    P.chiama(ctx.registro, ctx, "sviluppo_apri", {"proposta": lav.id}, turno=2)
    mv = P.valida(M_GIORNI)
    n = est.archivio.nuova_candidata(mv, {"estensione.py": CODICE.encode()}, "Dario",
                                     {"eseguiti": 6, "falliti": 0},
                                     {"rischi": [], "sintassi": []}, lav.id, True)
    svc.finisci(lav, "fatto", estensione={"nome": "meteo_codificato", "versione": n},
                messaggio="ho preparato l'estensione")
    return lav, n


def prova_collaudo(tmp, iso):
    print("— 4. il collaudo con più input")
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    lav, n = al_collaudo(ctx, est, svc)
    svs = svc.sviluppi
    sv = svs.corrente("u1")
    verifica("siamo al collaudo della versione con citta e giorni", sv.fase == "collaudo", sv.fase)
    dt = svs.dati_turno(sv)
    verifica("i dati del turno elencano gli input con tipo e descrizione, e come passarli",
             "citta (testo, obbligatorio): nome della città" in dt
             and "giorni (numero intero): quanti giorni di previsioni" in dt
             and "argomenti" in dt and "non tutto in dati" in dt, dt[-600:])
    ctx.turno, ctx.regole = 5, []
    out = P.chiama(reg, ctx, "sviluppo_collauda", {"argomenti": {"citta": "Pratofiorito",
                                                                 "giorni": 3}})
    verifica("argomenti = {citta, giorni}: la versione in prova li riceve per nome",
             "A Pratofiorito per 3 giorni" in j(out)
             and out.get("argomenti_passati") == {"citta": "Pratofiorito", "giorni": 3}, j(out))
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "Pratofiorito, 5 giorni"})
    verifica("il caso della DGX: dati «Pratofiorito, 5 giorni» → citta e giorni "
             "(collaudo_input_dal_testo)", "A Pratofiorito per 5 giorni" in j(out)
             and "collaudo_input_dal_testo" in ctx.regole, j(out))
    out = P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "Borgoverde per i prossimi 2 giorni"})
    verifica("«Borgoverde per i prossimi 2 giorni» → citta = Borgoverde, giorni = 2",
             "A Borgoverde per 2 giorni" in j(out), j(out))
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_collauda", {"argomenti": {"citta":
                                                                 "Pratofiorito, 5 giorni"}})
    verifica("argomenti sbagliati del modello: arrivano come sono (citta con i giorni)",
             "Non ho trovato Pratofiorito, 5 giorni" in j(out)
             and "collaudo_input_dal_testo" not in ctx.regole, j(out))
    testo = svs.testo_per_agente(sv)
    verifica("il contesto per chi l'ha scritto: gli input della versione e gli argomenti veri di "
             "ogni collaudo (citta=\"Pratofiorito, 5 giorni\")",
             "Input della versione in prova: citta (testo" in testo
             and 'citta="Pratofiorito, 5 giorni"' in testo and 'giorni=3' in testo,
             testo[:900])
    scheda = svs.testo_scheda(sv)
    verifica("…e sulla scheda dello sviluppo", 'citta="Pratofiorito, 5 giorni"' in scheda,
             scheda[:600])
    ctx.turno = 7
    P.chiama(reg, ctx, "sviluppo_correggi", {"problema": "mette i giorni nella città"})
    lc = svc.lavori[-1]
    verifica("sviluppo_correggi: nei vincoli i collaudi con gli argomenti passati",
             "argomenti passati: citta=\"Pratofiorito, 5 giorni\"" in lc.vincoli, lc.vincoli[:800])

    print("   contrari della conversione dei dati")
    m = P.valida(M_GIORNI)
    casi = {"Via Roma 5": {"citta": "Via Roma 5"},
            "Valfiorita, 5": {"citta": "Valfiorita, 5"},
            "5 giorni": {"citta": "5 giorni"},
            "citta: Borgoverde, giorni: 4": {"citta": "Borgoverde", "giorni": "4"},
            "Pratofiorito, 2 giorni e 3 giorni": {"citta": "Pratofiorito, 2 giorni e 3 giorni"}}
    for d, atteso in casi.items():
        verifica(f"«{d}» → {atteso}", ts._argomenti(m, d) == atteso, str(ts._argomenti(m, d)))
    verifica("un'estensione con un solo input: «Pratofiorito, 5 giorni» tutto in citta",
             ts._argomenti(P.valida(M_COD), "Pratofiorito, 5 giorni")
             == {"citta": "Pratofiorito, 5 giorni"})


# ═══════════════════════════ 5. l'analisi ═══════════════════════════

def prova_analisi(tmp, iso):
    print("— 5. l'analisi: niente testo ripetuto, «avanti» accetta")
    verifica("la modifica uguale alla specifica: la specifica resta",
             ts._con_modifica(DESCRIZIONE, "aggiungere la possibilità di scegliere quanti giorni "
                                           "di previsioni vedere") == DESCRIZIONE)
    verifica("…anche se ci sta dentro", ts._con_modifica(DESCRIZIONE + "; il nome codificato",
                                                         "scegliere quanti giorni")
             == DESCRIZIONE + "; il nome codificato")
    verifica("contrario: una modifica nuova si aggiunge",
             ts._con_modifica(DESCRIZIONE, "anche il vento") == DESCRIZIONE
             + ". Con questa modifica: anche il vento")

    cfg, reg, ctx, est, svc = ambiente(tmp / "a", iso)
    lav, n = al_collaudo(ctx, est, svc)
    svs = svc.sviluppi
    sv = svs.corrente("u1")
    ctx.turno, ctx.regole = 10, []
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia":
                                                "aggiungere la possibilità di scegliere quanti "
                                                "giorni di previsioni vedere"})
    verifica("il caso della DGX (17:01): «Ho capito così: X.» senza «Con questa modifica: X»",
             "Con questa modifica" not in S.detta(out) and sv.fase == "analisi"
             and sv.proposto, S.detta(out))
    ctx.turno, ctx.regole = 14, []           # tre turni in mezzo: l'offerta è scaduta
    k = len(svc.lavori)
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"})
    verifica("il caso della DGX (17:02): «l'analisi è corretta, implementala così» → avanti "
             "accetta la specifica letta, il lavoro parte (niente domanda ripetuta)",
             len(svc.lavori) == k + 1 and sv.fase == "sviluppo"
             and "sviluppo_avanti_accetta" in ctx.regole and "Ho capito così" not in S.detta(out),
             S.detta(out))

    cfg, reg, ctx, est, svc = ambiente(tmp / "c", iso)
    lav, n = al_collaudo(ctx, est, svc)
    sv = svc.sviluppi.corrente("u1")
    ctx.turno = 10
    P.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": "anche il vento"})
    prop = sv.proposto
    ctx.turno, ctx.regole = 14, []
    k = len(svc.lavori)
    out = P.chiama(reg, ctx, "sviluppo_apri", {"proposta": prop, "tipo": "estensione"})
    verifica("…anche con sviluppo_apri e la proposta scaduta (misura con gemma4): il lavoro "
             "parte, niente «chiedimelo di nuovo»",
             len(svc.lavori) == k + 1 and sv.fase == "sviluppo"
             and "sviluppo_proposta_scaduta" in ctx.regole
             and "chiedimelo di nuovo" not in S.detta(out), S.detta(out))
    out = P.chiama(reg, ctx, "sviluppo_apri", {"proposta": "L99", "tipo": "estensione"},
                   turno=15)
    verifica("contrario: una proposta che non è dello sviluppo → «chiedimelo di nuovo»",
             "chiedimelo di nuovo" in S.detta(out), S.detta(out))

    cfg, reg, ctx, est, svc = ambiente(tmp / "b", iso)
    lav, n = al_collaudo(ctx, est, svc)
    sv = svc.sviluppi.corrente("u1")
    ctx.turno = 10
    P.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi", "cambia": "anche il vento"})
    sc = ctx.speaker_ctx
    sc.identified_by, sc.conferma_breve = "breve", False
    ctx.turno, ctx.regole = 14, []
    k = len(svc.lavori)
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"})
    verifica("contrario: un «sì» breve che non basta → la specifica riproposta, niente lavoro",
             len(svc.lavori) == k and "Ho capito così" in S.detta(out)
             and "sviluppo_avanti_accetta" not in ctx.regole, S.detta(out))


# ═══════════════════════════ 6. il titolo della persona ═══════════════════════════

def prova_titolo(tmp, iso):
    print("— 6. il titolo dato dalla persona resta")
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    lav, n = al_collaudo(ctx, est, svc)
    rev = est.revisione("meteo_codificato")
    verifica("la revisione non dice «che ora si chiama «Meteo città»»: resta «Meteocittà»",
             "ora si chiama" not in rev["frase"] and "«Meteocittà»" in rev["frase"], rev["frase"])
    verifica("…sulla scheda il titolo proposto dall'agente, e come cambiarlo",
             "l'agente proponeva «Meteo città»" in rev["testo"], rev["testo"][:400])
    ctx.speaker_ctx.sfida_superata = True
    out = est.gestisci(ctx, "approva", "meteo_codificato")
    verifica("approvata: «Fatto: «Meteocittà» è attiva»",
             S.detta(out).startswith("Fatto: «Meteocittà» è attiva, versione"), S.detta(out))
    verifica("…e l'elenco dice ancora «Meteocittà»", "«Meteocittà» (attiva" in
             S.detta(est.gestisci(ctx, "elenca")))


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-giro4-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    prova_modifica(tmp0 / "modifica", iso)
    prova_breve(tmp0 / "breve", iso)
    prova_collaudo(tmp0 / "collaudo", iso)
    prova_analisi(tmp0 / "analisi", iso)
    prova_titolo(tmp0 / "titolo", iso)
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
