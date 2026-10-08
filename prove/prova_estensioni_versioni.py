"""Versioni di un'estensione, a voce (08/10/2026, giro 10: caso vero della DGX del 07/10 sera col
26B, riscritto con nomi di fantasia).

Il caso: c'era «Meteo Borgoverde e Valfiorita» (città fisse). La persona chiede un'estensione
che dica il meteo di una città qualunque; il modello la chiama «Meteo Città» e il confronto
approssimato del nome la trasforma nella versione 2 di quella che c'era, con il titolo nuovo
«Meteo per città». Poi: «attiva l'estensione Meteocittà» → azione inesistente «attiva»,
«riattiva» → «Fatto: è di nuovo attiva» (la vecchia), quattro turni per approvare la nuova;
approvata, «invoca l'estensione meteo per città su Bergamo» tre volte → sempre web_cerca;
«modificala» → lavoro_affida di codice → «impossibile: non posso modificare le estensioni»,
detto come «Il lavoro di un agente chiede anche dei codici o delle password» (riferire);
«Com'è andata l'estensione?» → «Vuoi sentire il risultato?».

A secco, con il docker finto (prove/docker_finto.py) e un servizio dei lavori finto:
1. sviluppo_apri: un nome simile a quello di un'estensione che c'è è un'estensione NUOVA
   (detto nella risposta, regola `estensione_nuova_accanto`); `modifica` fa la versione nuova
   (con i file e il nome); `modifica` che non c'è → l'elenco al modello;
2. l'annuncio e l'elenco di una versione nuova con il titolo di prima e quello nuovo, cosa fa e
   come approvarla; niente «di l'»;
3. estensione_gestisci: «attiva» → approva con una versione da approvare (prima della politica,
   `estensioni_azione_sinonimo`), → riattiva senza; «riattiva» di una già attiva non dice
   «Fatto» e propone la versione nuova (`estensione_gia_attiva`); i contrari;
4. approvata: la frase dice cosa fa adesso, il risultato dà al modello il tool e l'input;
5. dati del turno EST_NOMINATA_MSG (`estensione_nominata`): la frase che nomina l'estensione,
   anche storpiata, con «è cambiata da poco»; contrari (frase senza nome, rete spenta, nome di
   una parola dentro un'altra parola);
6. lavoro_affida di codice che cambia un'estensione → sviluppo_apri con modifica
   (`delega_estensione`); contrari: «estensione» dei file, il titolo senza la parola;
   l'analisi della richiesta con l'esito «estensione»;
7. lavoro_stato con un lavoro d'estensione finito: la versione da approvare e la domanda;
8. il registro dei turni di una risposta interrotta dal nome a metà della sua unica frase:
   «risposta» (sentita) vuota e «risposta_inviata» con la frase, ripulita come la risposta (la
   frase di sfida), e per un ospite niente; contrario: non interrotta, nessun campo in più.

    python prove\\prova_estensioni_versioni.py
"""

import dataclasses
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_estensioni as P  # noqa: E402
from calliope.agenti import richiesta as ar  # noqa: E402
from calliope.agenti import risultato as rs  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.estensioni.servizio import azione_vera  # noqa: E402
from calliope.tools import agenti as ta  # noqa: E402
from calliope.tools import estensioni as te  # noqa: E402
from prove.prova_conferma_unica import LavoriFinti as _LavoriFinti  # noqa: E402


class LavoriFinti(_LavoriFinti):
    """Come quello di prova_conferma_unica, con i vincoli dati all'agente."""
    def nuovo(self, tipo, compito, persona=None, persona_nome=None, livello="familiare",
              formato="", modello="", vincoli="", dati=None):
        lav = super().nuovo(tipo, compito, persona, persona_nome, livello, formato, modello,
                            vincoli, dati)
        lav.vincoli = vincoli
        return lav
from prove.prova_politica import Copione  # noqa: E402


class Registra(Copione):
    """Il modello finto che ricorda i messaggi ricevuti."""
    def __init__(self):
        super().__init__()
        self.visti = []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        yield from super().stream(messages, tools)

    def warmup(self, messages, tools):
        return {"prompt": 10}

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def detta(r: dict) -> str:
    return str(r.get("risposta_finale") or r.get("conferma") or "")


M1 = P.manifesto("meteo_citta", "Meteo Borgoverde e Valfiorita",
                 "Dice il meteo attuale a Borgoverde e Valfiorita.",
                 permessi={"rete": {"pubblica": True, "host": ["api.open-meteo.com"]}})
M2 = P.manifesto("meteo_citta", "Meteo per città", "Dice il meteo attuale in una città.",
                 input_={"type": "object", "properties": {"citta": {
                     "type": "string", "description": "nome della città"}},
                     "required": ["citta"]},
                 permessi={"rete": {"pubblica": True, "host": ["api.open-meteo.com",
                                                                "geocoding-api.open-meteo.com"]}})
CODICE = '''
def esegui(dati, calliope):
    return {"da_dire": "A " + str(dati.get("citta") or "Borgoverde") + " ci sono 18 gradi."}
'''


def ambiente(tmp: Path, iso):
    cfg, reg, ctx, est, casa, liste = P.ambiente(tmp, iso)
    for s in te.estensioni_specs():
        reg.register(s)
    ctx.regole = []
    ctx.turno = 1
    return cfg, reg, ctx, est


def candidata_v2(est):
    """La versione 2 «Meteo per città» da approvare, come da un lavoro."""
    mv = P.valida(M2)
    n = est.archivio.nuova_candidata(mv, {"estensione.py": CODICE.encode()}, "Dario",
                                     {"eseguiti": 11, "falliti": 0}, {"rischi": [],
                                                                       "sintassi": []},
                                     "L1", True)
    return mv, n


def prova_crea(tmp: Path, iso):
    print("— 1. sviluppo_apri: nuova o versione nuova")
    cfg, reg, ctx, est = ambiente(tmp, iso)
    P.installa(est, M1, CODICE)
    svc = LavoriFinti()
    ctx.lavori = svc
    ctx.politica_accettata = True       # «sì» con la voce alla domanda della politica
    compito = ("Crea un'estensione che permetta di chiedere il meteo di una città "
               "specifica e restituisca le condizioni attuali.")
    r = te._estensione_crea(ctx, compito=compito, nome="Meteo Città")
    # Dal 08/10 (giro 3, DGX 15:36: «Modifica l'estensione Meteocittà…» senza modifica → una
    # nuova accanto, riscritta da zero): la prima volta la scelta torna al modello
    verifica("«Meteo Città» senza modifica, simile a meteo_citta: niente lavoro, la scelta al "
             "modello (estensione_simile_scelta)",
             r.get("ok") is False and not svc.avviati
             and "modifica = \"meteo_citta\"" in r.get("cosa_fare", "")
             and "NUOVA accanto" in r.get("cosa_fare", "")
             and "estensione_simile_scelta" in ctx.regole, json.dumps(r, ensure_ascii=False))
    # Il modello richiama uguale nella stessa risposta: vuole davvero una nuova accanto
    r = te._estensione_crea(ctx, compito=compito, nome="Meteo Città")
    lav = svc.avviati[-1] if svc.avviati else None
    verifica("…richiamata uguale: un'estensione nuova, non la versione 2 di "
             "meteo_citta", lav is not None and lav.estensione is None
             and "calliope_estensione.py" in lav.file_iniziali
             and "estensione.py" not in lav.file_iniziali, str(getattr(lav, "estensione", "")))
    verifica("…e la frase lo dice: «Sarà un'estensione nuova: «Meteo Borgoverde e Valfiorita», "
             "che c'è già, resta com'è.»",
             detta(r).startswith("Sarà un'estensione nuova: «Meteo Borgoverde e Valfiorita», "
                                 "che c'è già, resta com'è.")
             and "estensione_nuova_accanto" in ctx.regole, detta(r))
    ctx.regole.clear()
    r = te._estensione_crea(ctx, compito="Fai dire il meteo di una città qualunque.",
                            modifica="meteo per città")
    lav = svc.avviati[-1]
    verifica("modifica (anche col titolo della versione vecchia, storpiato): versione nuova di "
             "meteo_citta, con i suoi file", lav.estensione == "meteo_citta"
             and "estensione.py" in lav.file_iniziali and "stesso nome" in lav.vincoli
             and lav.titolo.startswith("Meteo Borgoverde"), f"{lav.estensione} {lav.titolo}")
    verifica("…e la frase dice che la versione di adesso resta in uso",
             detta(r).startswith("Sarà una versione nuova di «Meteo Borgoverde e Valfiorita»: "
                                 "quella di adesso resta in uso finché non approvi la nuova.")
             and "estensione_nuova_accanto" not in ctx.regole, detta(r))
    n = len(svc.avviati)
    r = te._estensione_crea(ctx, compito="Fai dire il meteo.", modifica="oroscopo del giorno")
    verifica("modifica di un'estensione che non c'è: niente lavoro, l'elenco al modello",
             r.get("ok") is False and len(svc.avviati) == n
             and "«Meteo Borgoverde e Valfiorita» (meteo_citta, attiva)" in r.get("cosa_fare", ""),
             json.dumps(r, ensure_ascii=False)[:200])
    r = te._estensione_crea(ctx, compito="Una funzione che converte le unità di misura.",
                            nome="Convertitore")
    verifica("contrario: un nome che non somiglia a nessuna: nessun avviso",
             not detta(r).startswith("Sarà") and svc.avviati[-1].estensione is None, detta(r))
    ctx.politica_accettata = False
    r = te._estensione_crea(ctx, compito=compito, nome="Meteo Città")
    verifica("senza la conferma della politica: la proposta («Procedo?») con l'avviso davanti",
             detta(r).startswith("Sarà un'estensione nuova") and detta(r).endswith("?"),
             detta(r))
    spec = reg.get("sviluppo_apri")
    verifica("descrizione: CAMBIA con modifica, nome per una nuova",
             "modifica = il suo nome" in spec.description and "nome: un nome breve per "
             "un'estensione nuova" in spec.description
             and "modifica" in spec.parameters["properties"])


def prova_annuncio_elenco(tmp: Path, iso):
    print("— 2. annuncio ed elenco di una versione nuova")
    cfg, reg, ctx, est = ambiente(tmp, iso)
    P.installa(est, M1, CODICE)
    vecchio = est.archivio.manifesto("meteo_citta")
    mv, n = candidata_v2(est)
    c = est._presenta(mv, n, {"eseguiti": 11}, True, {"rischi": []}, vecchio)
    verifica("annuncio: «la versione 2 di «Meteo Borgoverde e Valfiorita», che ora si chiama "
             "«Meteo per città»: dice il meteo attuale in una città»",
             c["frase"].startswith("ho preparato la versione 2 di «Meteo Borgoverde e "
                                   "Valfiorita», che ora si chiama «Meteo per città»: Dice il "
                                   "meteo attuale in una città.")
             and " di l'" not in c["frase"] and c["frase"].endswith("Vuoi approvarla?"),
             c["frase"][:160])
    verifica("…la domanda in sospeso dice la stessa cosa",
             c["in_sospeso"]["cosa"].startswith("approvare la versione 2 di «Meteo Borgoverde"))
    c1 = est._presenta(P.valida(M1), 1, {"eseguiti": 1}, True, {"rischi": []})
    verifica("contrario: la prima versione resta «l'estensione «…»»",
             c1["frase"].startswith("ho preparato l'estensione «Meteo Borgoverde e Valfiorita»"),
             c1["frase"][:80])
    stesso = dict(M2, titolo="Meteo Borgoverde e Valfiorita")
    c2 = est._presenta(P.valida(stesso), 2, {"eseguiti": 1}, True, {"rischi": []}, vecchio)
    verifica("contrario: stesso titolo, niente «che ora si chiama»",
             "che ora si chiama" not in c2["frase"] and "la versione 2 di «Meteo Borgoverde"
             in c2["frase"], c2["frase"][:100])
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "elenca"}, turno=2)
    verifica("elenco: la versione 2 con il suo titolo, cosa fa e come usarla",
             "«Meteo Borgoverde e Valfiorita» (attiva, versione 1; c'è una versione nuova da "
             "approvare, la 2, «Meteo per città»: dice il meteo attuale in una città)" in detta(r)
             and detta(r).endswith("Per usare una versione nuova, dimmi di approvarla."),
             detta(r))
    est.archivio.rifiuta("meteo_citta", n)
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "elenca"}, turno=3)
    verifica("contrario: senza versioni nuove l'elenco di sempre",
             detta(r) == "Ho un'estensione: «Meteo Borgoverde e Valfiorita» (attiva).", detta(r))


def prova_gestisci(tmp: Path, iso):
    print("— 3. «attiva», «riattiva» e i sinonimi")
    cfg, reg, ctx, est = ambiente(tmp, iso)
    P.installa(est, M1, CODICE)
    mv, n = candidata_v2(est)
    a = est.archivio
    casi = [("attiva", "meteo_citta", "approva"), ("Attiva", "Meteo Città", "approva"),
            ("abilita", "meteo_citta", "approva"), ("usa", "meteo_citta", "approva"),
            ("disabilita", "meteo_citta", "disattiva"), ("elimina", "meteo_citta", "rimuovi"),
            ("approva", "meteo_citta", "approva"), ("riattiva", "meteo_citta", "riattiva"),
            ("indovina", "meteo_citta", "indovina")]
    for detto, nome, atteso in casi:
        from calliope.estensioni.servizio import _nome
        verifica(f"azione «{detto}» su «{nome}» → «{atteso}»",
                 azione_vera(detto, _nome(nome, a), a) == atteso)
    ctx.regole.clear()
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "attiva", "nome": "Meteo Città"},
                 turno=2)
    s = ctx.speaker_ctx.sfida
    verifica("«attiva l'estensione Meteocittà» con la versione 2 da approvare: la frase di "
             "sfida per approvarla (non «azione sconosciuta»)",
             "ripeti" in detta(r).lower() and s is not None
             and detta(r).startswith("Per approvare la versione 2 di «Meteo Borgoverde e "
                                     "Valfiorita», che ora si chiama «Meteo per città», ripeti")
             and s.argomenti.get("azione") == "approva"
             and "estensioni_azione_sinonimo" in ctx.regole, detta(r))
    ctx.speaker_ctx.sfida = None
    ctx.regole.clear()
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "riattiva", "nome": "Meteo Città"},
                 turno=3)
    sosp = r.get("in_sospeso") or {}
    verifica("«riattiva» di una già attiva: niente «Fatto», com'è e la versione nuova",
             "Fatto" not in detta(r) and detta(r).startswith(
                 "«Meteo Borgoverde e Valfiorita» è già attiva, versione 1. C'è la versione "
                 "nuova 2 di «Meteo Borgoverde e Valfiorita», che ora si chiama «Meteo per "
                 "città»: dice il meteo attuale in una città. Vuoi approvarla?")
             and sosp.get("argomenti") == {"azione": "approva", "nome": "meteo_citta"}
             and "estensione_gia_attiva" in ctx.regole and a.voce("meteo_citta")["attiva"] == 1,
             detta(r))
    a.rifiuta("meteo_citta", n)
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "riattiva", "nome": "meteo_citta"},
                 turno=4)
    verifica("contrario: già attiva e niente da approvare: «è già attiva», senza domande",
             detta(r) == "«Meteo Borgoverde e Valfiorita» è già attiva, versione 1."
             and not r.get("in_sospeso"), detta(r))
    P.chiama(reg, ctx, "estensione_gestisci", {"azione": "disattiva", "nome": "meteo_citta"},
             turno=5)
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "attiva", "nome": "meteo_citta"},
                 turno=6)
    verifica("contrario: «attiva» di una disattivata senza versioni nuove = riattiva",
             detta(r) == "Fatto: «Meteo Borgoverde e Valfiorita» è di nuovo attiva."
             and reg.get("est_meteo_citta") is not None, detta(r))
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "indovina", "nome": "meteo_citta"},
                 turno=7)
    verifica("contrario: un'azione che non c'è resta un errore",
             "azione sconosciuta" in str(r.get("errore")), str(r))
    spec = reg.get("estensione_gestisci")
    verifica("descrizione: «attiva la versione nuova» è approva; per usarla il tool est_",
             "«attiva la versione nuova»" in spec.description and "est_" in spec.description
             and spec.prepara is not None)


def prova_approvata(tmp: Path, iso):
    print("— 4. la versione 2 approvata")
    cfg, reg, ctx, est = ambiente(tmp, iso)
    P.installa(est, M1, CODICE)
    candidata_v2(est)
    ctx.speaker_ctx.sfida_superata = True
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "approva", "nome": "meteo_citta"},
                 turno=2)
    ctx.speaker_ctx.sfida_superata = False
    verifica("la frase dice cosa fa adesso",
             detta(r) == "Fatto: «Meteo per città» è attiva, versione 2: dice il meteo attuale "
                         "in una città. Da adesso puoi chiedermela.", detta(r))
    verifica("per il modello: il tool, l'input e che prima era un'altra versione",
             r.get("tool") == "est_meteo_citta" and r.get("input") == ["citta"]
             and "versione di prima" in r.get("nota", ""), json.dumps(r, ensure_ascii=False))
    spec = reg.get("est_meteo_citta")
    verifica("il tool ha lo schema e la descrizione della versione 2",
             "citta" in spec.parameters.get("properties", {})
             and spec.description.startswith("Dice il meteo attuale in una città"),
             spec.description)
    r = P.chiama(reg, ctx, "est_meteo_citta", {"citta": "Bergamo"}, turno=3)
    verifica("e risponde per la città data", "Bergamo" in json.dumps(r, ensure_ascii=False),
             json.dumps(r, ensure_ascii=False)[:160])
    return cfg, reg, ctx, est


FRASI_SI = [
    "Perfetto, ora vorrei che tu invocassi l'estensione meteo per città e la ricercassi su "
    "Bergamo.",
    "Calliope in realtà ti ho chiesto l'estensione Medio per città.",
    "L'eronia non è molto vaga. Io ho bisogno che tu invochi meteo per città, cercando il meteo "
    "per Bergamo.",
    "Non devi guardare su internet. Invoca l'estensione Meteo per città su Bergamo.",
    "Attiva l'estensione Meteocittà.",
]
FRASI_NO = ["Che tempo fa a Bergamo?", "Com'è il meteo oggi?", "Mettiamo per la città un "
            "albero.", "Quanti per cento di pioggia?", "Ho visto il meteorologo in città."]


def prova_nominata(tmp: Path, iso):
    print("— 5. dati del turno: l'estensione nominata")
    cfg, reg, ctx, est = prova_approvata(tmp, iso)
    for f in FRASI_SI:
        trovate = [e["nome"] for e in est.nominate(f)]
        verifica(f"nominata: «{f[:60]}»", trovate == ["meteo_citta"], str(trovate))
    for f in FRASI_NO:
        verifica(f"contrario, non nominata: «{f}»", est.nominate(f) == [])
    P.installa(est, P.manifesto("tris", "Tris", "Propone una partita a tris."), CODICE)
    verifica("un titolo di una parola: solo a parola intera",
             [e["nome"] for e in est.nominate("Facciamo una partita a tris?")] == ["tris"]
             and est.nominate("Ho comprato i tristi biscotti.") == [])
    b = Brain(cfg, reg, ctx)
    b.backend = Registra()
    b.conv_owner = "dario"
    b.last_turn_at = time.monotonic()
    b.backend.risposte = [[("text", "Va bene.")]]
    "".join(b.stream_reply(FRASI_SI[0], "amministra"))
    visti = " ".join(str(m.get("content") or "") for m in b.backend.visti[-1]
                     if m.get("role") == "system")
    verifica("Brain: EST_NOMINATA_MSG con il tool, cosa fa, l'input e «cambiata da poco»",
             "nomina la tua estensione «Meteo per città» (versione 2): è il tool "
             "est_meteo_citta, «Dice il meteo attuale in una città», input: citta" in visti
             and "È cambiata da poco" in visti and "estensione_nominata" in b.last_rules,
             visti[-400:])
    b.backend.risposte = [[("text", "Ci sono 18 gradi.")]]
    "".join(b.stream_reply("Che tempo fa a Bergamo?", "amministra"))
    visti = " ".join(str(m.get("content") or "") for m in b.backend.visti[-1])
    verifica("contrario: «Che tempo fa a Bergamo?» senza dati del turno sull'estensione",
             "nomina la tua estensione" not in visti
             and "estensione_nominata" not in b.last_rules)
    v = est.archivio.voce("meteo_citta")["versioni"]["2"]
    v["approvata"] = "2026-10-01T10:00:00"
    msg = b._estensioni_nominate(FRASI_SI[3]) or ""
    verifica("approvata da giorni: senza «è cambiata da poco»",
             "est_meteo_citta" in msg and "cambiata" not in msg, msg)
    b.cfg.llm_reti_spente = ["estensione_nominata"]
    verifica("rete spenta: niente dati del turno", b._estensioni_nominate(FRASI_SI[0]) is None)
    b.cfg.llm_reti_spente = []
    P.chiama(reg, ctx, "estensione_gestisci", {"azione": "disattiva", "nome": "meteo_citta"},
             turno=9)
    msg = b._estensioni_nominate(FRASI_SI[0]) or ""
    # (dal 08/10 la frase che dice «estensione» riceve l'elenco vero, con lo stato)
    verifica("contrario: disattivata (niente tool): non è «nominata», nell'elenco disattivata",
             "nomina la tua estensione" not in msg
             and "«Meteo per città» (disattivata" in msg, msg)
    verifica("…ma per cambiarla la si trova ancora (tutte=True)",
             [e["nome"] for e in est.nominate(FRASI_SI[0], tutte=True)] == ["meteo_citta"])


def prova_delega(tmp: Path, iso):
    print("— 6. lavoro_affida che cambia un'estensione, analisi della richiesta")
    cfg, reg, ctx, est = ambiente(tmp, iso)
    P.installa(est, M1, CODICE)
    mv, n = candidata_v2(est)
    est.archivio.approva("meteo_citta", n, "Dario")
    est.aggiorna_tool()
    svc = LavoriFinti()
    ctx.lavori = svc
    ctx.politica_accettata = True
    vero = ("Modifica la logica dell'estensione 'Meteo per città' in modo che, invece di attingere "
            "a un database locale preimpostato, utilizzi una ricerca web per fornire il meteo di "
            "qualsiasi città indicata dall'utente.")
    r = ta._delega_lavoro(ctx, tipo="codice", compito=vero)
    lav = svc.avviati[-1] if svc.avviati else None
    verifica("il compito vero della DGX: sviluppo_apri con modifica = meteo_citta, già "
             "confermato", lav is not None and lav.tipo == "estensione"
             and lav.estensione == "meteo_citta" and "delega_estensione" in ctx.regole
             and detta(r).startswith("Sarà una versione nuova di «Meteo per città»"), detta(r))
    for compito in ("Scrivi un programma che legge il meteo per città da un file CSV.",
                    "Cambia l'estensione dei file .txt in .md in una cartella.",
                    "Scrivi un programma che calcola la radice quadrata."):
        k = len(svc.avviati)
        ctx.regole.clear()
        r = ta._delega_lavoro(ctx, tipo="codice", compito=compito)
        verifica(f"contrario: «{compito[:50]}» resta un lavoro di codice",
                 "delega_estensione" not in ctx.regole
                 and (len(svc.avviati) == k or svc.avviati[-1].tipo == "codice"), detta(r))
    # L'analisi della richiesta: «ESTENSIONE» per un lavoro di codice
    js = json.dumps({"impossibile": "ESTENSIONE", "punti": {}, "domande": [], "specifica": "",
                     "nome": "", "fonte_url": "", "gia_fatto": "", "come_chiederlo": ""})
    e = ar.interpreta(js, "codice")
    verifica("analisi: «ESTENSIONE» per un lavoro di codice → esito estensione",
             e.esito == "estensione" and not e.motivo, e.per_registro())
    e = ar.interpreta(js.replace("ESTENSIONE", "serve la rete di casa"), "codice")
    verifica("contrario: un motivo vero resta impossibile", e.esito == "impossibile")
    e = ar.interpreta(js, "estensione")
    verifica("contrario: per una richiesta d'estensione «ESTENSIONE» non è un esito",
             e.esito == "impossibile")
    verifica("analisi: il prompt del codice dice che le estensioni si fanno con un'altra "
             "richiesta", "scrivi solo la parola ESTENSIONE" in ar.capacita(cfg, "codice"))

    class Analizzatore:
        def recente(self, *a):
            return None

        def analizza(self, *a, **k):
            return ar.Esito(esito="estensione", secondi=0.5)

        def log(self, *a):
            pass

        def ricorda(self, *a):
            pass
    svc.analizzatore = Analizzatore()
    k = len(svc.avviati)
    r = ta._delega_lavoro(ctx, tipo="codice", compito="Correggi l'estensione del meteo che "
                                                      "sbaglia le città.")
    verifica("analisi con esito estensione: niente lavoro, nessuna frase detta, il modello "
             "richiama sviluppo_apri (con l'elenco)", len(svc.avviati) == k
             and not detta(r) and "sviluppo_apri" in r.get("cosa_fare", "")
             and "(meteo_citta, attiva)" in r.get("cosa_fare", ""), json.dumps(r, ensure_ascii=False))


def prova_lavori_stato(tmp: Path, iso):
    print("— 7. lavoro_stato con un lavoro d'estensione finito")
    cfg, reg, ctx, est = ambiente(tmp, iso)
    P.installa(est, M1, CODICE)
    mv, n = candidata_v2(est)
    lav = SimpleNamespace(id="L1", tipo="estensione", stato="fatto", titolo="Meteo Città",
                          persona="u1", fine=time.time() - 60, dal_disco=False,
                          risultato={"esito": "fatto", "estensione": {
                              "nome": "meteo_citta", "versione": n, "frase": "…"}})
    svc = SimpleNamespace(stato=lambda *a, **k: "Non ho lavori in corso.",
                          in_attesa=lambda *a: [], offerta_ripresa=lambda *a: None,
                          attivi=lambda *a, **k: [])
    ctx.lavori = svc
    vecchio = rs.recenti
    rs.recenti = lambda *a, **k: [lav]
    try:
        r = ta._lavori_stato(ctx)
        sosp = r.get("in_sospeso") or {}
        verifica("«Com'è andata l'estensione?»: la versione da approvare e «Vuoi approvarla?»",
                 "Ha preparato la versione 2 di «Meteo Borgoverde e Valfiorita», che ora si "
                 "chiama «Meteo per città»: è da approvare. Vuoi approvarla?" in detta(r)
                 and sosp.get("tool") == "estensione_gestisci"
                 and sosp.get("argomenti") == {"azione": "approva", "nome": "meteo_citta"},
                 detta(r))
        est.archivio.approva("meteo_citta", n, "Dario")
        r = ta._lavori_stato(ctx)
        verifica("approvata: «è attiva, versione 2», senza domande",
                 detta(r).endswith("«Meteo per città» è attiva, versione 2.")
                 and not r.get("in_sospeso"), detta(r))
        lav.tipo, lav.risultato = "ricerca", {"esito": "fatto"}
        r = ta._lavori_stato(ctx)
        verifica("contrario: un lavoro di ricerca: «Vuoi sentire il risultato?»",
                 detta(r).endswith("Vuoi sentire il risultato?"), detta(r))
    finally:
        rs.recenti = vecchio


def prova_registro_interrotta():
    print("— 8. registro dei turni di una risposta interrotta")
    import queue
    import threading
    import types
    import prova_minori_pericolo as MP
    from calliope import corsie
    from calliope.ciclo import Ciclo, Servizi, Turno
    from calliope.config import Config
    from calliope.cortesia import Cortesia
    from calliope.turnlog import TurnLog
    cfg = Config()
    cfg.speaker_id_enabled = False
    cfg.debug_audio_dir = None
    voce, chi = MP.Voce(), MP.ChiParla()
    frase = ("Non ho lavori in corso. Gli ultimi finiti: «Meteo Città», oggi alle 18:23. "
             "Vuoi sentire il risultato?")

    class Cervello(MP.Cervello):
        regole = []

        def stream_reply(self, text, level, context=None, **k):
            yield self.risposta

        def rules_fired(self):
            return list(self.regole)
    cervello = Cervello()
    ascolto = MP.Ascolto(voce)
    instr = types.SimpleNamespace(dopo_turno=lambda x: x, inizio_voce=lambda: None,
                                  persona=lambda *a: None, origine=lambda: {},
                                  annuncia_verso=lambda *a, **k: None,
                                  risposta_scritta=lambda *a: None)
    srv = Servizi(cfg, registry=MP.Persone(), instradamento=instr, cortesia=Cortesia(),
                  turns=types.SimpleNamespace(write=lambda r: None),
                  attiva_minori=lambda: False, guardiano=None, wake=object(),
                  barge_in=True, barge_voice=False)
    srv.controllo_impronte[0] = time.monotonic()
    annunci = types.SimpleNamespace(agenda=queue.Queue(), documenti=None, installazioni=None,
                                    lavori=None, estensioni=None)
    c = Ciclo(srv, corsie.Corsia("locale"), ascolto, voce, chi, cervello,
              types.SimpleNamespace(), annunci, None, threading.Event())
    voce.ciclo = c

    def turno(testo, risposta, modo):
        chi.current_speaker = "Carlo"
        cervello.risposta = risposta
        ascolto.modo, ascolto.inizio = modo, len(voce.detto)
        t = Turno(text=testo, speaker_name="Carlo", barged=False,
                  prof_turno=MP.Persone().get("Carlo"))
        c.rec = {}
        c._rispondi(t)
        c._registra_risposta(t)
        c._dopo_la_risposta(t)
        return dict(c.rec)

    rec = turno("Com'è andata l'estensione?", frase, "nome")
    verifica("interrotta a metà dell'unica frase: «risposta» vuota, «risposta_inviata» con la "
             "frase", rec.get("interrotta") is True and rec.get("risposta") == ""
             and rec.get("risposta_inviata") == frase, json.dumps(rec, ensure_ascii=False)[:300])
    cervello.regole = ["sfida_voce"]
    rec = turno("Approvala.", "Per approvare l'estensione «Meteo per città», ripeti: girasole, "
                              "matita, orologio, novantanove.", "nome")
    verifica("interrotta durante la frase di sfida: le parole non restano nel registro",
             "girasole" not in json.dumps(rec, ensure_ascii=False)
             and rec.get("risposta_inviata", "").endswith("ripeti: …"), str(rec.get(
                 "risposta_inviata")))
    cervello.regole = []
    rec = turno("Che ore sono?", "Sono le 18:49.", None)
    verifica("contrario: non interrotta, la risposta intera e nessun campo in più",
             rec.get("risposta") == "Sono le 18:49." and "risposta_inviata" not in rec
             and not rec.get("interrotta"), str(rec))
    cartella = Path(tempfile.mkdtemp(prefix="calliope-turni-"))
    log = TurnLog(str(cartella))
    log._write({"inizio": "2026-10-07T18:48:50", "livello": "ospite", "testo": "ciao",
                "risposta": "", "risposta_inviata": frase, "interrotta": True})
    riga = json.loads(next(cartella.glob("*.jsonl")).read_text(encoding="utf-8"))
    verifica("ospite: niente testo della risposta inviata nel registro",
             riga.get("risposta_inviata") is None, str(riga))


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-est-versioni-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    prova_crea(tmp0 / "crea", iso)
    prova_annuncio_elenco(tmp0 / "annuncio", iso)
    prova_gestisci(tmp0 / "gestisci", iso)
    prova_nominata(tmp0 / "nominata", iso)
    prova_delega(tmp0 / "delega", iso)
    prova_lavori_stato(tmp0 / "stato", iso)
    prova_registro_interrotta()
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
