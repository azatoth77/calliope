"""La modalità sviluppo, versione 2, a secco (08/10/2026, calliope/sviluppo.py,
tools/sviluppo.py, agenti/ciclo.py e agenti/servizio.py per le tappe;
docs/ricerche/2026-10-08-modalita-sviluppo.md § 9).

Il giro di prova vero della DGX (08/10, 11:06–11:32, satellite dello studio, 26B), riscritto con
nomi di fantasia: lo sviluppo «Meteo per città»; il collaudo con Bergamo va, con una città di due
parole che il geocoder finto non trova («Pratofiorito Maggiore», al posto di quella vera) dice
«Impossibile cercare la città»; «Perché?» improvvisato dalla voce; «fai revisionare il codice
all'agente» tornava all'analisi; «Ok, chiuso a long» (storpiato) chiudeva lo sviluppo senza
conferma con l'agente al lavoro; il lavoro finito annunciato vecchio stile; «prova con…» →
«C'è di mezzo il lavoro di un agente» → «Non c'è nessuno sviluppo aperto da provare».

1. nomi nuovi: i tool che ci sono e quelli che non ci sono più; i nomi vecchi valgono ancora
   (`tool_nome_vecchio`); lavoro_affida di codice passa allo sviluppo (`lavoro_codice_sviluppo`);
2. apertura esplicita, specifica letta, titolo leggibile («meteo_città» → «Meteo città»);
3. collaudo fallito → caso per l'agente e «Lo faccio correggere?»; i contrari (riuscito, rifiuto
   prima dell'esecuzione);
4. sviluppo_chiedi: il contesto conservato (specifica, collaudi, diario e passi dell'agente, file,
   fonti), sola lettura (nessun lavoro), dato non fidato, tempo massimo, la proposta di correzione;
5. sviluppo_correggi: un lavoro sui file della versione provata, la specifica resta, i collaudi
   falliti e la diagnosi nei vincoli; un collaudo riuscito giudicato sbagliato diventa il caso;
6. chiusura: con l'agente al lavoro diventa sospensione; altrimenti chiede conferma e chiude solo
   al «sì» a quella domanda, mai da una frase sola; il contesto conservato se ne va;
7. lavoro finito a sviluppo sospeso: si riapre al collaudo («Con cosa provo? … di nuovo con
   «Pratofiorito Maggiore»»), e «prova con…» è un passo interno (niente «C'è di mezzo…»);
8. tappe con il servizio dei lavori vero e l'Ollama finto: al tetto delle passate il lavoro va in
   attesa con il contesto e il rapporto (segnali di giro a vuoto misurati dal codice), «continua»
   fa un giro nuovo con la nota, poi finisce; firme degli errori e segnali.

    python prove\\prova_sviluppo_v2.py
"""

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_estensioni as P  # noqa: E402
import prova_sviluppo as S  # noqa: E402
from calliope import politica  # noqa: E402
from calliope.tools import agenti as ta  # noqa: E402
from calliope.tools import sviluppo as ts  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


detta = S.detta

CITTA_FINTA = "Pratofiorito Maggiore"
# La candidata del giro vero: un geocoder (qui finto, un dizionario) che non trova le città di
# due parole, e allora risponde con un errore
CODICE_GEO = '''
GEO = {"bergamo": (45.69, 9.67), "borgoverde": (45.5, 9.2), "valfiorita": (45.6, 9.1),
       "lodi": (45.31, 9.5)}


def esegui(dati, calliope):
    citta = str(dati.get("citta") or "").strip()
    if citta.lower() not in GEO:
        return {"errore": "Impossibile cercare la città"}
    return {"da_dire": "A " + citta + " ci sono 18 gradi."}
'''


class AgenteFinto:
    """Il cliente del modello dell'agente per sviluppo_chiedi: registra le richieste e risponde a
    copione (o aspetta, per il tempo massimo)."""

    def __init__(self, risposta=None, ritardo=0.0):
        self.richieste, self.risposta, self.ritardo = [], risposta, ritardo

    def chat(self, body, **_):
        self.richieste.append(body)
        if self.ritardo:
            time.sleep(self.ritardo)
        return {"content": json.dumps(self.risposta, ensure_ascii=False)}

    def interrompi(self, *a):
        pass


def ambiente(tmp, iso):
    cfg, reg, ctx, est, svc = S.ambiente(tmp, iso)
    for s in ta.agenti_specs():
        reg.register(s)
    svc.cfg = cfg
    svc.imp = SimpleNamespace(modello="agente-finto")
    svc.cliente = AgenteFinto({"voce": "Il geocoder non trova i nomi di due parole: cerca solo "
                                       "la prima parola esatta.",
                               "dettagli": "In estensione.py la ricerca usa GEO.get(citta.lower()) "
                                           "e il dizionario ha solo nomi di una parola: per "
                                           "«Pratofiorito Maggiore» manca la chiave.",
                               "serve_correzione": True,
                               "cosa_correggere": "cercare la città con il nome intero e "
                                                  "dire «non trovata» invece di un errore"})
    P.installa(est, S.M1, S.CODICE1)
    return cfg, reg, ctx, est, svc


def candidata(est, lav_id="L1"):
    mv = P.valida(S.M2)
    return est.archivio.nuova_candidata(mv, {"estensione.py": CODICE_GEO.encode()}, "Dario",
                                        {"eseguiti": 4, "falliti": 0},
                                        {"rischi": [], "sintassi": []}, lav_id, True)


def contesto_finto(lav):
    """La conversazione dell'agente com'è a lavoro finito (Agente.codice: lav.contesto)."""
    lav.contesto = {"tipo": "codice", "gestore": {}, "piano": {"capacita": ["rete_pubblica"]},
                    "messages": [
                        {"role": "system", "content": "sistema"},
                        {"role": "user", "content": "Compito: il meteo di una città"},
                        {"role": "assistant", "content": "Uso il geocoder di Open-Meteo.",
                         "tool_calls": [{"function": {"name": "scrivi_file", "arguments": {
                             "percorso": "estensione.py", "contenuto": CODICE_GEO}}}]},
                        {"role": "tool", "tool_name": "scrivi_file",
                         "content": "{\"ok\": true}"},
                        {"role": "assistant", "content": "",
                         "tool_calls": [{"function": {"name": "esegui_test",
                                                      "arguments": {}}}]},
                        {"role": "tool", "tool_name": "esegui_test",
                         "content": "{\"passano\": true, \"uscita\": \"4 passed\"}"}]}
    lav.risultato = {"riassunto": "Estensione del meteo per città con il geocoder.",
                     "esito": "fatto", "test": {"eseguiti": 4, "falliti": 0}}


def apri_e_finisci(ctx, est, svc):
    """Dario: «voglio un'estensione…», «sì», il lavoro finisce con la candidata del giro vero."""
    ctx.turno = 1
    r = S.P.chiama(ctx.registro, ctx, "sviluppo_apri", {
        "tipo": "estensione", "compito": "un'estensione che dica il meteo di una città "
                                          "qualunque", "nome": "meteo_città"})
    if "estensione_simile_scelta" in ctx.regole:
        # Dal 08/10 (giro 3): nome simile senza modifica → la scelta al modello, che la cambia
        r = S.P.chiama(ctx.registro, ctx, "sviluppo_apri", {
            "tipo": "estensione", "compito": "un'estensione che dica il meteo di una città "
                                              "qualunque", "modifica": "meteo_citta"})
    lav = svc.offerte["u1"]["lavoro"]
    r2 = S.P.chiama(ctx.registro, ctx, "sviluppo_apri", {"proposta": lav.id}, turno=2)
    n = candidata(est, lav.id)
    contesto_finto(lav)
    svc.sviluppi.conserva(lav)
    item = svc.finisci(lav, "fatto", estensione={"nome": "meteo_citta", "versione": n},
                       test={"eseguiti": 4, "falliti": 0},
                       messaggio="ho preparato l'estensione «Meteo per città»… Vuoi approvarla?")
    return r, r2, lav, item, n


# ═══════════════════════════ 1. nomi ═══════════════════════════

def prova_nomi(tmp, iso):
    print("— 1. nomi nuovi dei tool, i vecchi che valgono ancora")
    from calliope.tools.builtin import build_registry
    reg = build_registry(agenti=True)
    nomi = {s["function"]["name"] for s in reg.all_schemas()}
    nuovi = {"lavoro_affida", "lavoro_stato", "lavoro_risultato", "lavoro_rispondi",
             "lavoro_annulla", "sviluppo_apri", "sviluppo_passo", "sviluppo_collauda",
             "sviluppo_chiedi", "sviluppo_correggi", "programma_esegui"}
    vecchi = {"delega_lavoro", "lavori_stato", "risultato_lavoro", "lavori_rispondi",
              "lavori_annulla", "estensione_crea", "estensioni_gestisci", "lavori_esegui",
              "sviluppo", "sviluppo_prova"}
    verifica("i nomi nuovi ci sono, i vecchi no", nuovi <= nomi and not (vecchi & nomi),
             str((nuovi - nomi) | (vecchi & nomi)))
    tipi = reg.get("lavoro_affida").parameters["properties"]["tipo"]["enum"]
    verifica("lavoro_affida senza il codice (tipo: documento, ricerca, altro)",
             "codice" not in tipi and "ricerca" in tipi, str(tipi))
    verifica("sviluppo_apri: tipo estensione o programma",
             reg.get("sviluppo_apri").parameters["properties"]["tipo"]["enum"]
             == ["estensione", "programma"])
    verifica("politica e valore conoscono i tool nuovi",
             all(n in politica.CLASSI for n in nuovi | {"estensione_gestisci"})
             and politica.CLASSI["sviluppo_chiedi"].classe == politica.SICURO
             and politica.CLASSI["sviluppo_chiedi"].fonte == "agente")
    from calliope import valore
    verifica("valore: un programma esegue codice (E3), un'estensione prepara (E2), chiudi E1",
             valore.effetto("sviluppo_apri", {"tipo": "programma"}) == valore.E3
             and valore.effetto("sviluppo_apri", {"tipo": "estensione"}) == valore.E2
             and valore.effetto("sviluppo_passo", {"azione": "chiudi"}) == valore.E1)
    # i nomi vecchi (una conversazione di prima, un'azione in sospeso) valgono ancora
    cfg, reg2, ctx, est, svc = ambiente(tmp / "nomi", iso)
    ctx.registro = reg2
    ctx.regole = []
    out = P.chiama(reg2, ctx, "estensione_crea", {"compito": "un'estensione che converte le "
                                                             "valute", "nome": "Valute"}, turno=1)
    verifica("il nome vecchio estensione_crea vale come sviluppo_apri (tool_nome_vecchio)",
             "tool_nome_vecchio" in ctx.regole and "Va bene così" in detta(out), detta(out))
    svs = svc.sviluppi
    svs.sospendi(svs.corrente("u1"))
    ctx.regole = []
    out = P.chiama(reg2, ctx, "lavoro_affida", {"tipo": "codice", "compito": "uno script che "
                                                "rinomina le foto"}, turno=4)
    sv = svs.corrente("u1")
    verifica("lavoro_affida di codice passa allo sviluppo di un programma "
             "(lavoro_codice_sviluppo)",
             "lavoro_codice_sviluppo" in ctx.regole and sv is not None and sv.tipo == "programma"
             and (out.get("in_sospeso") or {}).get("tool") == "sviluppo_apri", detta(out))


# ═══════════════════════════ 2. apertura ═══════════════════════════

def prova_apertura(tmp, iso):
    print("— 2. apertura esplicita, specifica letta, titolo leggibile")
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    ctx.registro = reg
    ctx.regole = []
    r, r2, lav, item, n = apri_e_finisci(ctx, est, svc)
    f = detta(r)
    verifica("«Entriamo in modalità sviluppo per «…». Ho capito così: … Va bene così, o la "
             "cambiamo?»",
             # (con un nome simile a un'estensione che c'è, prima l'avviso del giro 10; dal
             # giro 3 dell'08/10 il modello sceglie modifica: il titolo è quello che c'è)
             "Entriamo in modalità sviluppo per «Meteo Borgoverde e Valfiorita». Ho capito "
             "così: " in f
             and f.endswith("Va bene così, o la cambiamo?") and "meteo di una città" in f
             and "sviluppo_apertura" in ctx.regole, f)
    sosp = r.get("in_sospeso") or {}
    verifica("…con il «sì» verso sviluppo_apri proposta = l'id",
             sosp.get("tool") == "sviluppo_apri"
             and sosp.get("domanda", "").endswith("Va bene così, o la cambiamo?") and sosp.get("argomenti", {}).get("proposta")
             == lav.id, str(sosp))
    verifica("il «sì» (sviluppo_apri con proposta) avvia il lavoro: sviluppo",
             "Ci lavoro" in detta(r2), detta(r2))
    from calliope.sviluppo import leggibile
    verifica("titolo leggibile: «meteo_città» → «Meteo città», «MeteoSemplice» (gemma4) → «Meteo "
             "semplice»; un titolo di una persona resta",
             leggibile("meteo_città") == "Meteo città"
             and leggibile("MeteoSemplice") == "Meteo semplice"
             and leggibile("Meteo per città") == "Meteo per città" and leggibile("TV") == "TV")
    svs = svc.sviluppi
    sv = svs.corrente("u1")
    verifica("lavoro finito: «… è pronto: siamo al collaudo. … Con cosa provo?», mai «Vuoi "
             "approvarla?»",
             sv.fase == "collaudo" and "è pronto: siamo al collaudo" in item["messaggio"]
             and item["messaggio"].endswith("Con cosa provo?")
             and "Vuoi approvarla" not in item["messaggio"]
             and item["in_sospeso"]["tool"] == "sviluppo_collauda", item["messaggio"])
    # Una seconda proposta nello stesso sviluppo (ritorno all'analisi): niente «Entriamo»
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi",
                                                "cambia": "anche l'umidità"}, turno=6)
    verifica("una proposta dopo, nello stesso sviluppo: la specifica letta, senza «Entriamo»",
             detta(out).startswith("Ho capito così:") and "umidità" in detta(out)
             and detta(out).endswith("Va bene così, o la cambiamo?"), detta(out))


# ═══════════════════════════ 3. collaudo fallito ═══════════════════════════

def prova_collaudo_fallito(tmp, iso):
    print("— 3. collaudo fallito → caso per l'agente, «Lo faccio correggere?»")
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    ctx.registro = reg
    apri_e_finisci(ctx, est, svc)
    sv = svc.sviluppi.corrente("u1")
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "Bergamo"}, turno=5)
    verifica("«prova con Bergamo»: riuscito, il risultato in busta (non fidato)",
             "A Bergamo ci sono 18 gradi" in json.dumps(out, ensure_ascii=False)
             and sv.collaudi[-1]["ok"] and "sviluppo_collaudo_fallito" not in ctx.regole)
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_collauda", {"dati": CITTA_FINTA}, turno=6)
    f = detta(out)
    verifica("«prova con Pratofiorito Maggiore»: non va, la frase del codice e «Lo faccio "
             "correggere?»",
             f.startswith(f"La prova con «{CITTA_FINTA}» non è andata") and
             f.endswith("Lo faccio correggere?") and "sviluppo_collaudo_fallito" in ctx.regole
             and "Impossibile" not in f, f)
    sosp = out.get("in_sospeso") or {}
    verifica("…il «sì» va a sviluppo_correggi, con il caso", sosp.get("tool")
             == "sviluppo_correggi" and CITTA_FINTA in sosp["argomenti"]["problema"], str(sosp))
    verifica("…il collaudo è nello sviluppo come NON riuscito, con l'esito per l'agente",
             not sv.collaudi[-1]["ok"] and sv.collaudi[-1]["dati"] == CITTA_FINTA
             and "Impossibile" in sv.collaudi[-1]["esito"], str(sv.collaudi[-1]))
    verifica("…e sulla scheda", "non riuscito" in svc.sviluppi.testo_scheda(sv))
    from calliope.tools.sviluppo import _fallito
    verifica("_fallito: errore dell'esecuzione, campo errore, ok false; contrari: risultato "
             "buono, «non trovata» a parole",
             _fallito({"ok": False, "errore": "x"}, None)
             and _fallito({"ok": True, "risultati": {"errore": "y"}}, {"errore": "y"})
             and _fallito({"ok": True, "risultati": {"ok": False}}, {"ok": False})
             and not _fallito({"ok": True, "risultati": {"da_dire": "18 gradi"}},
                              {"da_dire": "18 gradi"})
             and not _fallito({"ok": True, "risultati": {"da_dire": "Non l'ho trovata."}},
                              {"da_dire": "Non l'ho trovata."}))


# ═══════════════════════════ 4. sviluppo_chiedi ═══════════════════════════

def prova_chiedi(tmp, iso):
    print("— 4. sviluppo_chiedi: il contesto conservato, sola lettura, dato non fidato")
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    ctx.registro = reg
    r, r2, lav, item, n = apri_e_finisci(ctx, est, svc)
    svs = svc.sviluppi
    sv = svs.corrente("u1")
    verifica("contesto conservato a lavoro finito (sviluppi/S1.json)",
             svs._file_contesto(sv).is_file() and svs.contesto(sv)["lavori"][0]["lavoro"]
             == lav.id)
    P.chiama(reg, ctx, "sviluppo_collauda", {"dati": CITTA_FINTA}, turno=5)
    lavori_prima = len(svc.lavori) + len(svc.offerte)
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_chiedi", {"domanda": "Perché?"}, turno=6)
    body = svc.cliente.richieste[-1]
    testo = body["messages"][1]["content"]
    verifica("la domanda va al modello dell'agente con il contesto: specifica, collaudi con gli "
             "esiti, diario e passi, file, fonti",
             "Perché?" in testo and "città qualunque" in testo and CITTA_FINTA in testo
             and "NON riuscito" in testo and "Impossibile cercare la città" in testo
             and "Uso il geocoder" in testo and "--- file estensione.py ---" in testo
             and "citta.lower() not in GEO" in testo and "geocoding-api.open-meteo.com" in testo,
             [k for k in ("Perché?", "città qualunque", CITTA_FINTA, "NON riuscito", "Impossibile cercare la città", "Uso il geocoder", "--- file estensione.py ---", "citta.lower() not in GEO", "geocoding-api.open-meteo.com") if k not in testo])
    verifica("…in sola lettura: niente strumenti, ragionamento spento, JSON; nessun lavoro nuovo",
             "tools" not in body and body.get("think") is False and body.get("format")
             and "SOLA LETTURA" in body["messages"][0]["content"]
             and len(svc.lavori) + len(svc.offerte) == lavori_prima)
    verifica("la risposta: frase breve per la voce, correzione proposta, niente risposta_finale "
             "(la dice il modello, in busta)",
             out.get("ok") and "due parole" in out.get("risposta", "") and out.get(
                 "serve_correzione") is True and "risposta_finale" not in out
             and (out.get("in_sospeso") or {}).get("tool") == "sviluppo_correggi"
             and "sviluppo_chiedi" in ctx.regole, json.dumps(out, ensure_ascii=False)[:300])
    spec = reg.get("sviluppo_chiedi")
    verifica("sviluppo_chiedi è non fidato con la fonte «agente», e annuncia l'attesa",
             spec.non_fidato and politica.fonte_di("sviluppo_chiedi", spec) == "agente"
             and spec.announce == ("Lo chiedo a chi l'ha scritta.",))
    verifica("la domanda e i dettagli sono nello sviluppo e sulla scheda",
             sv.chiesti and sv.chiesti[-1]["domanda"] == "Perché?" and sv.chiesti[-1]["correzione"]
             and "Domande a chi l'ha scritta" in svs.testo_scheda(sv))
    # tempo massimo: l'agente non risponde
    svc.cliente = AgenteFinto({"voce": "tardi", "serve_correzione": False}, ritardo=1.5)
    cfg.sviluppo_chiedi_s = 0.3
    ctx.regole = []
    t0 = time.monotonic()
    out = P.chiama(reg, ctx, "sviluppo_chiedi", {"domanda": "Come mai?"}, turno=7)
    verifica("tempo massimo (sviluppo_chiedi_s): lo dice, propone la correzione, non aspetta",
             time.monotonic() - t0 < 1.4 and "non mi risponde" in detta(out)
             and "sviluppo_chiedi_guasto" in ctx.regole
             and (out.get("in_sospeso") or {}).get("tool") == "sviluppo_correggi", detta(out))
    # contrari
    ctx.speaker_ctx = P.speaker("Bianca", "familiare")
    out = P.chiama(reg, ctx, "sviluppo_chiedi", {"domanda": "Perché?"}, turno=8)
    verifica("contrario: Bianca (familiare) non chiede", out.get("ok") is False, detta(out))
    ctx.speaker_ctx = P.speaker()


# ═══════════════════════════ 5. sviluppo_correggi ═══════════════════════════

def prova_correggi(tmp, iso):
    print("— 5. sviluppo_correggi: la correzione come passo a sé")
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    ctx.registro = reg
    r, r2, lav, item, n = apri_e_finisci(ctx, est, svc)
    svs = svc.sviluppi
    sv = svs.corrente("u1")
    spec_prima = sv.specifica
    P.chiama(reg, ctx, "sviluppo_collauda", {"dati": CITTA_FINTA}, turno=5)
    P.chiama(reg, ctx, "sviluppo_chiedi", {"domanda": "Perché?"}, turno=6)
    ctx.regole = []
    ctx.tool_in_sospeso = "sviluppo_correggi"
    out = P.chiama(reg, ctx, "sviluppo_correggi", {}, turno=7)
    ctx.tool_in_sospeso = None
    nuovo = svc.lavori[-1]
    verifica("«sì» a «Lo faccio correggere?»: un lavoro nuovo parte subito, fase sviluppo",
             nuovo.id != lav.id and nuovo.stato == "in_corso" and sv.fase == "sviluppo"
             and sv.lavoro == nuovo.id and getattr(nuovo, "correzione", False)
             and "sviluppo_correzione" in ctx.regole and sv.correzioni == 1, detta(out))
    verifica("…la frase dice che poi rifacciamo la prova con la città che non andava",
             f"rifacciamo la prova con «{CITTA_FINTA}»" in detta(out), detta(out))
    verifica("…la specifica non cambia (non è un ritorno all'analisi)",
             sv.specifica == spec_prima and not any(x.get("a") == "analisi" and x.get("da")
                                                   for x in sv.storia))
    verifica("…l'agente riparte dai file della versione provata, con i casi e la diagnosi",
             "citta.lower() not in GEO" in nuovo.file_iniziali.get("estensione.py", "")
             and "CORREZIONE" in nuovo.vincoli and CITTA_FINTA in nuovo.vincoli
             and "dizionario ha solo nomi di una parola" in nuovo.vincoli
             and "nome intero" in nuovo.vincoli and nuovo.estensione == "meteo_citta"
             and nuovo.tipo == "estensione", nuovo.vincoli[:300])
    verifica("…con le tappe accese (lavoro di uno sviluppo)", getattr(nuovo, "tappe", False))
    # Senza uno sviluppo aperto (misura con gemma4: «Correggi lo script di backup…» → qui)
    cfg3, reg3, ctx3, est3, svc3 = ambiente(tmp / "senza", iso)
    ctx3.regole, ctx3.user_text = [], "Correggi lo script di backup: non copia i file nascosti."
    out = P.chiama(reg3, ctx3, "sviluppo_correggi", {"problema": "non copia i file nascosti"},
                   turno=1)
    sv3 = svc3.sviluppi.corrente("u1")
    verifica("senza sviluppo aperto: è una richiesta nuova di codice (sviluppo_correggi_nuovo)",
             "sviluppo_correggi_nuovo" in ctx3.regole and sv3 is not None
             and sv3.tipo == "programma" and "backup" in sv3.richiesta
             and "Va bene così" in detta(out), detta(out))
    out = P.chiama(reg, ctx, "sviluppo_correggi", {}, turno=8)
    verifica("contrario: con l'agente già al lavoro non ne parte un altro",
             out.get("ok") is False and svc.lavori[-1] is nuovo, detta(out))
    # un collaudo riuscito che la persona giudica sbagliato
    cfg2, reg2, ctx2, est2, svc2 = ambiente(tmp / "giudizio", iso)
    ctx2.registro = reg2
    apri_e_finisci(ctx2, est2, svc2)
    sv2 = svc2.sviluppi.corrente("u1")
    P.chiama(reg2, ctx2, "sviluppo_collauda", {"dati": "Lodi"}, turno=5)
    P.chiama(reg2, ctx2, "sviluppo_correggi", {"problema": "deve dire anche se piove"}, turno=6)
    nuovo2 = svc2.lavori[-1]
    verifica("un collaudo riuscito ma sbagliato per la persona diventa il caso (giudizio)",
             sv2.collaudi[-1].get("giudizio") == "deve dire anche se piove"
             and "«Lodi»" in nuovo2.vincoli and "deve dire anche se piove" in nuovo2.vincoli,
             nuovo2.vincoli[:300])


# ═══════════════════════════ 6. chiusura ═══════════════════════════

def prova_chiusura(tmp, iso):
    print("— 6. chiudere: conferma, e con l'agente al lavoro diventa sospendere")
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    ctx.registro = reg
    apri_e_finisci(ctx, est, svc)
    svs = svc.sviluppi
    sv = svs.corrente("u1")
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "esci"}, turno=10)
    verifica("«Ok, chiuso a long» → sviluppo_passo(esci): chiede conferma, non chiude",
             sv.stato == "aperta" and detta(out).startswith("Chiudere lo sviluppo di «Meteo per "
                                                            "città»")
             and detta(out).endswith("Lo chiudo?")
             and "sospendi" in detta(out) and "non è ancora approvata" in detta(out)
             and "sviluppo_chiudi_conferma" in ctx.regole
             and (out.get("in_sospeso") or {}).get("argomenti") == {"azione": "chiudi"},
             detta(out))
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "chiudi"}, turno=10)
    verifica("contrario: richiamato nello stesso turno non chiude", sv.stato == "aperta")
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "chiudi"}, turno=11)
    verifica("contrario: il turno dopo ma senza il «sì» alla domanda (nessuna azione in "
             "sospeso) non chiude", sv.stato == "aperta", detta(out))
    ctx.tool_in_sospeso = "sviluppo_passo"
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "chiudi"}, turno=12)
    ctx.tool_in_sospeso = None
    verifica("il «sì» alla domanda: chiuso, e il contesto conservato se ne va",
             sv.stato == "chiusa" and sv.motivo == "uscita"
             and "torniamo alla conversazione normale" in detta(out)
             and not svs._file_contesto(sv).exists(), detta(out))
    # con l'agente al lavoro
    cfg2, reg2, ctx2, est2, svc2 = ambiente(tmp / "lavoro", iso)
    ctx2.registro = reg2
    ctx2.turno = 1
    P.chiama(reg2, ctx2, "sviluppo_apri", {"tipo": "estensione", "compito": "il meteo di una "
                                                                          "città qualunque"})
    lav = svc2.offerte["u1"]["lavoro"]
    P.chiama(reg2, ctx2, "sviluppo_apri", {"proposta": lav.id}, turno=2)
    sv2 = svc2.sviluppi.corrente("u1")
    ctx2.regole = []
    out = P.chiama(reg2, ctx2, "sviluppo_passo", {"azione": "chiudi"}, turno=3)
    verifica("con l'agente al lavoro «chiudi» diventa «sospendi», e lo dice",
             sv2.stato == "sospesa" and "invece di chiudere, sospendo" in detta(out)
             and "sviluppo_chiudi_sospende" in ctx2.regole, detta(out))
    return svc2, sv2, lav, ctx2, reg2, est2


# ═══════════════════════════ 7. riapertura ═══════════════════════════

def prova_riapertura(tmp, iso):
    print("— 7. lavoro finito a sviluppo sospeso: si riapre al collaudo")
    svc, sv, lav, ctx, reg, est = prova_chiusura(tmp / "chiusura", iso)
    svs = svc.sviluppi
    # un falso collaudo fallito di prima, per la frase («di nuovo con…»)
    sv.collaudi.append({"quando": time.time(), "dati": CITTA_FINTA, "ok": False,
                        "esito": "Impossibile cercare la città"})
    lav.correzione = True
    n = candidata(est, lav.id)
    item = svc.finisci(lav, "fatto", estensione={"nome": "meteo_citta", "versione": n},
                       messaggio="ho preparato l'estensione «Meteo per città»… Vuoi approvarla?")
    verifica("il lavoro finisce a sviluppo sospeso: riaperto al collaudo, annuncio nuovo",
             sv.stato == "aperta" and sv.fase == "collaudo"
             and "è pronto: siamo al collaudo" in item["messaggio"]
             and f"di nuovo con «{CITTA_FINTA}»" in item["messaggio"]
             and "ho preparato" not in item["messaggio"], item["messaggio"])
    verifica("…e «Con cosa provo?» in sospeso verso il collaudo",
             item["in_sospeso"]["tool"] == "sviluppo_collauda")
    # «prova con…» con il lavoro dell'agente di mezzo: passo interno
    ctx.speaker_ctx = P.speaker()
    ctx.politica = politica.Turno(testo=f"prova con {CITTA_FINTA}",
                                  contaminazione=frozenset({"agente"}), persona="u1",
                                  esterni=[("agente", "ho preparato l'estensione")])
    ctx.regole = []
    try:
        res = politica.controlla(reg.get("sviluppo_collauda"), "sviluppo_collauda",
                                 {"dati": CITTA_FINTA}, ctx)
    finally:
        ctx.politica = None
    # (con la politica per valore, accesa dal 09/10, il collaudo chiesto con la voce e la città
    # detta esegue già per la matrice: valore_voce)
    verifica("«prova con…» nello sviluppo riaperto: niente «C'è di mezzo…» (sviluppo_intento "
             "o valore_voce)",
             res is None and {"sviluppo_intento", "valore_voce"} & set(ctx.regole), str(res))
    out = P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "Bergamo"}, turno=9)
    verifica("…e il collaudo va (niente «Non c'è nessuno sviluppo aperto»)",
             "A Bergamo ci sono 18 gradi" in json.dumps(out, ensure_ascii=False), detta(out))
    # uno chiuso (vecchio «esci» del 08/10 mattina) con il lavoro in giro: si riapre anche lui
    cfg3, reg3, ctx3, est3, svc3 = ambiente(tmp / "chiuso", iso)
    ctx3.registro = reg3
    ctx3.turno = 1
    P.chiama(reg3, ctx3, "sviluppo_apri", {"tipo": "estensione", "compito": "il meteo"})
    lav3 = svc3.offerte["u1"]["lavoro"]
    P.chiama(reg3, ctx3, "sviluppo_apri", {"proposta": lav3.id}, turno=2)
    sv3 = svc3.sviluppi.corrente("u1")
    svc3.sviluppi.chiudi(sv3, "uscita")
    n3 = candidata(est3, lav3.id)
    item = svc3.finisci(lav3, "fatto", estensione={"nome": "meteo_citta", "versione": n3})
    verifica("uno sviluppo chiuso con il lavoro ancora in giro: riaperto al collaudo",
             sv3.stato == "aperta" and sv3.fase == "collaudo"
             and "siamo al collaudo" in item["messaggio"], item["messaggio"])


# ═══════════════════════════ 8. tappe ═══════════════════════════

def prova_tappe(tmp):
    print("— 8. tappe: limite del giro, rapporto con i segnali, «continua»")
    from calliope.agenti import Lavori, carica
    from calliope.agenti.ciclo import firma_errore, segnali_giro
    from calliope.config import Config
    from calliope.documenti.formato import FORMATI
    from calliope.sviluppo import Sviluppi
    from prove.ollama_finto import FakeOllama
    verifica("firma dell'errore dei test: l'ultima riga d'errore, senza numeri",
             firma_errore({"passano": False, "uscita": "File x.py, line 12\nAssertionError: 3 "
                                                       "!= 5"}) == "AssertionError: # != #"
             and firma_errore({"passano": True, "uscita": "ok"}) == "")
    finto = SimpleNamespace(segnali={"scritture": {"somma.py": 4, "test_somma.py": 1},
                                     "errori_test": ["A", "B", "B", "B"], "senza_novita": 7})
    seg = segnali_giro(finto, 24)
    verifica("segnali di giro a vuoto: file riscritto, stesso errore di fila, passate senza "
             "novità",
             seg["a_vuoto"] and seg["riscritti"][0] == ["somma.py", 4]
             and seg["volte_errore"] == 3 and seg["senza_novita"] == 7
             and "ha riscritto somma.py 4 volte" in seg["frasi"], str(seg))
    verifica("contrario: nessun segnale con un lavoro che va avanti",
             not segnali_giro(SimpleNamespace(segnali={"scritture": {"a.py": 1},
                                                       "errori_test": ["A", "B"],
                                                       "senza_novita": 2}), 24)["a_vuoto"])
    fake = FakeOllama(modelli=("agente-finto",)).avvia()
    try:
        cfg = Config()
        cfg.agenti_url = fake.url
        cfg.agenti_modello = "agente-finto"
        cfg.agenti_risultati = str(tmp / "risultati")
        cfg.agenti_sandbox = str(tmp / "sandbox")
        cfg.agenti_sandbox_motore = "processo"
        cfg.agenti_modelli = str(tmp / "modelli")
        cfg.llm_native_url = "http://127.0.0.1:9"
        cfg.agenti_max_passi = 3
        svc = Lavori(cfg, carica(cfg), log=lambda *a: None, formati=FORMATI)
        svs = svc.sviluppi = Sviluppi(cfg, tmp / "sandbox", svc)

        def scrivi(contenuto):
            return {"tool_calls": [{"name": "scrivi_file", "arguments": {
                "percorso": "somma.py", "contenuto": contenuto}}]}
        fake.copione = [scrivi("def somma(a, b):\n    return a - b\n"),
                        scrivi("def somma(a, b):\n    return a * b\n"),
                        scrivi("def somma(a, b):\n    return b - a\n"),
                        # il giro 2 (dopo «continua»)
                        scrivi("def somma(a, b):\n    return a + b\n"),
                        {"tool_calls": [{"name": "consegna", "arguments": {
                            "riassunto": "Somma corretta.", "esito": "fatto"}}]}]
        sv = svs.apri("dario-id", "Dario", "programma", "somma due numeri", titolo="Somma")
        lav = svc.nuovo("codice", "Scrivi una funzione che somma due numeri", "dario-id",
                        "Dario", "amministra")
        svs.avviato(lav)
        verifica("un lavoro dello sviluppo ha le tappe accese", lav.tappe is True)
        svc.avvia(lav)
        item = svc.done.get(timeout=30)
        r = lav.risultato
        verifica("al tetto delle passate: in attesa (tappa), non chiuso",
                 lav.stato == "in_attesa" and r.get("esito") == "tappa"
                 and r.get("tipo_limite") == "passate" and lav.contesto.get("tappa"),
                 f"{lav.stato} {r}")
        msg = item["messaggio"]
        verifica("il rapporto: la tappa, i segnali misurati dal codice, la scelta",
                 "si è fermato a una tappa" in msg and "ha finito le passate del giro" in msg
                 and "ha riscritto somma.py 3 volte" in msg
                 and msg.endswith("Continuo con un altro giro, vuoi cambiare qualcosa prima, o "
                                  "lo fermo?"), msg)
        verifica("…con la domanda in sospeso verso sviluppo_passo avanti (modalità sviluppo)",
                 (item.get("in_sospeso") or {}).get("tool") == "sviluppo_passo"
                 and item["in_sospeso"]["argomenti"] == {"azione": "avanti"}, str(item))
        verifica("…lo sviluppo resta allo sviluppo, e la riga del modello dice cosa fare",
                 sv.fase == "sviluppo" and "fermo a una tappa" in svs.riga_fase(sv))
        verifica("…il contesto dello sviluppo è conservato anche alla tappa",
                 svs.contesto(sv).get("lavori", [{}])[-1].get("esito") == "tappa")
        verifica("lavoro_stato lo dice", "è fermo a una tappa" in svc.stato("dario-id"))
        frase = svc.continua(lav, "prova con a + b")
        verifica("«cambia e continua»: un giro nuovo con la nota", frase
                 and frase.startswith("Continuo") and lav.giro == 2 and lav.passi0 == 3, frase)
        item = svc.done.get(timeout=30)
        verifica("il giro 2 riparte dal contesto con la nota e finisce (passate del giro, non "
                 "del lavoro)",
                 lav.stato == "fatto" and lav.passi == 5
                 and any("Hai un altro giro di lavoro" in str(m.get("content"))
                         and "prova con a + b" in str(m.get("content"))
                         for m in fake.richieste[-1]["messages"]), f"{lav.stato} {lav.passi}")
        verifica("…e il lavoro finito porta lo sviluppo al collaudo",
                 sv.fase == "collaudo" and "è pronto: siamo al collaudo" in item["messaggio"],
                 item["messaggio"])
        # contrario: un lavoro fuori da uno sviluppo al tetto si chiude come prima
        fake.copione = [scrivi("x = 1\n")] * 4
        lav2 = svc.nuovo("codice", "Un programma che non finisce", "dario-id", "Dario")
        svc.avvia(lav2)
        item = svc.done.get(timeout=30)
        verifica("contrario: fuori da uno sviluppo il tetto chiude il lavoro (limite)",
                 item["esito"] == "limite" and "ho fermato" in item["messaggio"],
                 item["messaggio"])
        svc.close()
    finally:
        fake.ferma()


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-sviluppo2-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    prova_nomi(tmp0 / "nomi", iso)
    prova_apertura(tmp0 / "apertura", iso)
    prova_collaudo_fallito(tmp0 / "collaudo", iso)
    prova_chiedi(tmp0 / "chiedi", iso)
    prova_correggi(tmp0 / "correggi", iso)

    prova_riapertura(tmp0 / "riapertura", iso)
    prova_tappe(tmp0 / "tappe")
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
