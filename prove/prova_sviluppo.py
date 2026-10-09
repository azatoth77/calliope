"""La modalità sviluppo, a secco (08/10/2026, calliope/sviluppo.py, tools/sviluppo.py,
docs/ricerche/2026-10-08-modalita-sviluppo.md).

Il caso vero (DGX, 07/10 sera, nomi di fantasia): «Meteo Borgoverde e Valfiorita» a città fisse e
la richiesta di un'estensione per una città qualunque, quaranta minuti di conversazione normale
con provare DOPO approvare. Qui lo stesso iter come stato a fasi, con il docker finto
(prove/docker_finto.py), un servizio dei lavori finto e Brain con un modello finto:

1. macchina a stati: apertura con sviluppo_apri, proposta (specifica), avvio (sviluppo),
   lavoro finito (collaudo, senza «Vuoi approvarla?»), errore e annullo, fasi del programma, su
   disco e riletta, scheda;
2. collaudo: la versione candidata provata prima dell'approvazione nel container finto, con la
   porta; impronta cambiata rifiutata; il tool est_ non c'è ancora; risultato in busta;
3. revisione (permessi, analisi, test, differenze con la versione approvata), attivazione con la
   frase di sfida, chiusura dello sviluppo all'approvazione;
4. ritorno all'analisi da qualunque fase: il lavoro in corso si ferma, la specifica nuova si
   propone con i file della versione provata;
5. sviluppi nuovi bloccati con uno aperto (estensioni, programmi, ricerche) e i contrari (le
   risposte all'analisi, la modifica della sua estensione);
6. Brain: dati del turno SVILUPPO_MSG, la riga del fuori tema in coda e i contrari (nominato,
   domanda, tool dello sviluppo, rete spenta, nessuno sviluppo);
7. sospensione dopo 30 minuti (non con l'agente al lavoro), ripresa a voce, una aperta per
   persona; promemoria del giorno a chi amministra, una volta;
8. programma: collaudo con programma_esegui, revisione, proposta di farne un'estensione se è grande
   (e non se è piccolo), promuovi con i file del programma;
9. politica: i passi interni senza «C'è di mezzo…» (`sviluppo_intento`) e i contrari (un'altra
   persona, scritto, nessuno sviluppo, un'altra estensione, un valore preso dal dato).

    python prove\\prova_sviluppo.py
"""

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
from calliope import politica  # noqa: E402
from calliope.agenti import servizio as srv  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.sviluppo import Sviluppi, misura_programma  # noqa: E402
from calliope.tools import agenti as ta  # noqa: E402
from calliope.tools import estensioni as te  # noqa: E402
from calliope.tools import sviluppo as ts  # noqa: E402
from calliope.tools.spec import ToolSpec  # noqa: E402
from prove.prova_politica import Copione  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def detta(r: dict) -> str:
    return str(r.get("risposta_finale") or r.get("conferma") or "")


class Lavori:
    """Il servizio dei lavori, quanto basta: proposta, offerta, conferma, avvio, annullo,
    l'elenco dei lavori e gli sviluppi."""

    def __init__(self, cfg, cartella):
        self.offerte, self.lavori, self.n = {}, [], 0
        self.isolamento = SimpleNamespace(pronto=True)
        self.modelli, self.analizzatore, self.estensioni = {}, None, None
        self.annullati = []
        self.log = lambda *a: None
        self.sviluppi = Sviluppi(cfg, cartella, self, log=self.log)
        self.esecuzioni = EsecuzioniFinte(self)

    def nuovo(self, tipo, compito, persona=None, persona_nome=None, livello="familiare",
              formato="", modello="", vincoli="", dati=None):
        self.n += 1
        lav = SimpleNamespace(id=f"L{self.n}", tipo=tipo, compito=compito, persona=persona,
                              persona_nome=persona_nome, titolo=srv.titolo_da(compito),
                              file_candidati=[], file_utente=None, estensione=None,
                              file_iniziali={}, on_scheda=None, formato=formato,
                              vincoli=vincoli, specifica="", stato="nuovo", passi=0,
                              passo="scrive il codice", risultato={}, gioco=False)
        return lav

    def serve_conferma(self, lav):
        return True

    def proponi(self, lav, turno):
        self.offerte[lav.persona] = {"lavoro": lav, "turno": turno}
        spec = str(getattr(lav, "specifica", "") or "")
        return (f"Ho capito così: {spec}. " if spec else "") + "Lo affido all'agente. Procedo?"

    def offerta(self, persona, turno):
        off = self.offerte.get(persona)
        return off if off and 1 <= turno - off["turno"] <= 3 else None

    def conferma(self, persona, ident, turno):
        off = self.offerta(persona, turno)
        if off is None or off["lavoro"].id != ident:
            return None
        self.offerte.pop(persona, None)
        return off["lavoro"]

    def avvia(self, lav):
        lav.stato = "in_corso"
        self.lavori.append(lav)
        return "Ci lavoro in secondo piano: ti avviso quando è pronto."

    def annulla(self, persona=None, tutti_di_tutti=False, quale="ultimo"):
        for lv in self.lavori:
            if lv.id == quale and lv.stato in ("in_coda", "in_corso", "in_attesa"):
                lv.stato = "annullato"
                self.annullati.append(lv.id)
                return {"ok": True, "frase": f"Ho fermato «{lv.titolo}»."}
        return {"ok": False, "frase": "niente"}

    def attivi(self, persona=None, attesa=False):
        return [lv for lv in self.lavori if lv.stato in ("in_coda", "in_corso")]

    def collegamento_guasto(self):
        return None

    def verifica_in_secondo_piano(self):
        pass

    def finisci(self, lav, stato="fatto", **ris):
        """Il lavoro finito, e il suo annuncio passato agli sviluppi come fa Lavori._annuncia."""
        lav.stato = stato
        lav.risultato = dict(ris)
        item = {"id": lav.id, "messaggio": ris.pop("messaggio", f"ho finito «{lav.titolo}»."),
                "stato": stato}
        if (lav.risultato.get("estensione") or {}).get("in_sospeso"):
            item["in_sospeso"] = lav.risultato["estensione"]["in_sospeso"]
        return self.sviluppi.lavoro_finito(lav, item)


class EsecuzioniFinte:
    def __init__(self, svc):
        self.svc, self.eseguiti = svc, []

    def ultimo_lavoro(self, persona, admin=False, quale=""):
        fatti = [lv for lv in self.svc.lavori if lv.tipo == "codice" and lv.stato == "fatto"]
        if quale:
            fatti = [lv for lv in fatti if lv.id == quale]
        return fatti[-1] if fatti else None

    def avvia(self, lav, dati, on_scheda=None, persona=None, persona_nome=None):
        self.eseguiti.append((lav.id, list(dati)))
        return SimpleNamespace(id="X1", sullo_schermo=False), ""

    def attendi(self, es, s):
        return True

    def frase(self, es):
        return "Il programma è finito bene: stampa 8."


M1 = P.manifesto("meteo_citta", "Meteo Borgoverde e Valfiorita",
                 "Dice il meteo attuale a Borgoverde e Valfiorita.",
                 permessi={"rete": {"pubblica": True, "host": ["api.open-meteo.com"]}})
M2 = P.manifesto("meteo_citta", "Meteo per città", "Dice il meteo attuale in una città.",
                 input_={"type": "object", "properties": {"citta": {
                     "type": "string", "description": "nome della città"}},
                     "required": ["citta"]},
                 permessi={"rete": {"pubblica": True, "host": ["api.open-meteo.com",
                                                                "geocoding-api.open-meteo.com"]}})
CODICE1 = '''
def esegui(dati, calliope):
    return {"da_dire": "A Borgoverde ci sono 18 gradi."}
'''
CODICE2 = '''
def esegui(dati, calliope):
    citta = str(dati.get("citta") or "").strip()
    if citta.lower() == "atlantide":
        return {"da_dire": "Non ho trovato la città " + citta + "."}
    return {"da_dire": "A " + citta + " ci sono 18 gradi."}
'''


def ambiente(tmp: Path, iso):
    cfg, reg, ctx, est, casa, liste = P.ambiente(tmp, iso)
    for s in te.estensioni_specs(crea=True) + ts.sviluppo_specs():
        reg.register(s)
    svc = Lavori(cfg, tmp / "lavori")
    svc.estensioni = est
    est.sviluppi = svc.sviluppi
    ctx.lavori = svc
    ctx.regole = []
    ctx.turno = 1
    return cfg, reg, ctx, est, svc


def candidata(est, codice=CODICE2, m=M2, test_passano=True):
    mv = P.valida(m)
    n = est.archivio.nuova_candidata(mv, {"estensione.py": codice.encode()}, "Dario",
                                     {"eseguiti": 4, "falliti": 0}, {"rischi": [],
                                                                       "sintassi": []},
                                     "L1", test_passano)
    return n


def apri_e_avvia(ctx, est, svc, compito="Un'estensione che dica il meteo di una città "
                                        "qualunque, presa da Open-Meteo."):
    """La richiesta di Dario (voce), la proposta e il «sì»: sviluppo aperto, lavoro avviato."""
    ctx.turno = 1
    r = te._estensione_crea(ctx, compito=compito, nome="Meteo per città")
    if "estensione_simile_scelta" in ctx.regole:
        # Dal 08/10 (giro 3) un nome simile senza modifica torna al modello: cambiare quella
        # che c'è o farne una nuova accanto. Qui il modello sceglie di cambiarla
        r = te._estensione_crea(ctx, compito=compito, nome="Meteo per città",
                                modifica="meteo_citta")
    lav = svc.offerte["u1"]["lavoro"]
    lav.specifica = ("dice il meteo attuale di una città qualunque; se la città non esiste lo "
                     "dice")
    svc.sviluppi.proposto(lav)
    ctx.turno = 2
    r2 = ta._delega_lavoro(ctx, proposta=lav.id)
    return r, r2, lav


# ═══════════════════════════ 1. macchina a stati ═══════════════════════════

def prova_stati(tmp: Path, iso):
    print("— 1. macchina a stati")
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    svs = svc.sviluppi
    r, r2, lav = apri_e_avvia(ctx, est, svc)
    sv = svs.corrente("u1")
    verifica("sviluppo_apri di chi amministra apre lo sviluppo (sviluppo_aperto)",
             sv is not None and "sviluppo_aperto" in ctx.regole and sv.tipo == "estensione",
             str(ctx.regole))
    verifica("la proposta è in analisi; il «sì» passa allo sviluppo con il lavoro",
             sv.fase == "sviluppo" and sv.lavoro == lav.id and sv.proposto is None
             and "città qualunque" in sv.specifica, f"{sv.fase} {sv.lavoro} {sv.specifica}")
    verifica("fasi dell'estensione: 2 di 5, fatta analisi, mancano tre",
             svs.dove(sv).startswith("siamo allo sviluppo (2 di 5): fatta analisi; mancano "
                                     "collaudo, revisione e attivazione"), svs.dove(sv))
    n = candidata(est)
    item = svc.finisci(lav, "fatto", estensione={
        "nome": "meteo_citta", "versione": n,
        "in_sospeso": {"tool": "estensione_gestisci", "argomenti": {"azione": "approva"}}},
        messaggio="ho preparato l'estensione «Meteo per città»: … Vuoi approvarla?")
    verifica("lavoro finito: collaudo, senza «Vuoi approvarla?» né l'approvazione in sospeso",
             sv.fase == "collaudo" and "Vuoi approvarla?" not in item["messaggio"]
             and "siamo al collaudo" in item["messaggio"]
             and item["messaggio"].endswith("Con cosa provo?")
             and (item.get("in_sospeso") or {}).get("tool") == "sviluppo_collauda"
             and sv.estensione == "meteo_citta" and sv.versione == n, json.dumps(item,
                                                                                ensure_ascii=False))
    # su disco: un altro servizio legge lo stesso file
    altro = Sviluppi(cfg, tmp / "lavori", svc)
    s2 = altro.corrente("u1")
    verifica("su disco: riletto dopo un «riavvio», stessa fase e stessa estensione",
             s2 is not None and s2.fase == "collaudo" and s2.estensione == "meteo_citta"
             and s2.id == sv.id)
    # riavvio a metà sviluppo: il lavoro non c'è più, e uno rifatto con lo stesso titolo vale
    sv.fase, sv.lavoro = "sviluppo", lav.id
    svs._salva()
    dopo = Sviluppi(cfg, tmp / "lavori", svc)
    s3 = dopo.corrente("u1")
    verifica("riavvio a metà sviluppo: senza lavoro, con la nota «interrotto»",
             s3.fase == "sviluppo" and s3.lavoro is None and "riavvio" in s3.nota
             and "interrotto da un riavvio" in dopo.riga_fase(s3))
    rifatto = svc.nuovo("estensione", "x", "u1", "Dario")
    rifatto.titolo, rifatto.estensione = lav.titolo, "meteo_citta"
    rifatto.stato, rifatto.risultato = "fatto", {"estensione": {"nome": "meteo_citta",
                                                                "versione": n}}
    item = dopo.lavoro_finito(rifatto, {"messaggio": "ho preparato… Vuoi approvarla?"})
    verifica("…il lavoro rifatto dopo «Lo rifaccio?» porta lo sviluppo al collaudo",
             s3.fase == "collaudo" and s3.lavoro == rifatto.id
             and "siamo al collaudo" in item["messaggio"], item["messaggio"])
    sv.fase, sv.lavoro = "collaudo", lav.id
    svs._salva()
    card = svs.scheda(sv)
    md = card.get("markdown") or ""
    verifica("scheda: chiave sviluppo:S1, fasi con quella di adesso, specifica",
             card.get("chiave") == f"sviluppo:{sv.id}" and "**adesso: collaudo**" in md
             and "fatta: analisi" in md and "manca: revisione" in md and "Specifica" in md,
             md[:300])
    # un errore: resta allo sviluppo senza lavoro
    sv.fase = "sviluppo"
    lav2 = svc.nuovo("estensione", "x", "u1", "Dario")
    lav2.stato = "in_corso"
    svc.lavori.append(lav2)
    sv.lavoro = lav2.id
    item = svc.finisci(lav2, "errore", motivo="ha dovuto fermarlo: tetto delle passate",
                       messaggio="non sono riuscita a finire «x»: tetto delle passate.")
    verifica("lavoro fallito: lo sviluppo resta aperto, allo sviluppo, senza lavoro",
             sv.fase == "sviluppo" and sv.lavoro is None and sv.stato == "aperta"
             and "lo rifaccio così com'è" in item["messaggio"]
             and (item.get("in_sospeso") or {}).get("tool") == "sviluppo_passo",
             item["messaggio"])
    verifica("riga per il modello: il lavoro non è andato → analisi",
             "non è andato" in svs.riga_fase(sv))
    # programma: quattro fasi
    pr = svs.apri("u2", "Bianca", "programma", "somma due numeri")
    verifica("programma: quattro fasi, niente attivazione",
             pr.fasi() == ("analisi", "sviluppo", "collaudo", "revisione")
             and "4" in svs.dove(pr))
    # una richiesta d'estensione impossibile chiude lo sviluppo appena aperto
    tmp2 = tmp / "imp"
    cfg2, reg2, ctx2, est2, svc2 = ambiente(tmp2, iso)
    from calliope.agenti import richiesta as ar
    svc2.analizzatore = SimpleNamespace(
        recente=lambda *a: None, ricorda=lambda *a: None, log=lambda *a: None,
        analizza=lambda *a, **k: ar.Esito(esito="impossibile", motivo="serve la rete di casa"))
    te._estensione_crea(ctx2, compito="spegni il router di casa ogni notte")
    verifica("analisi «impossibile»: lo sviluppo appena aperto si chiude (non blocca gli altri)",
             svc2.sviluppi.corrente("u1") is None
             and any(s.stato == "chiusa" for s in svc2.sviluppi.sviluppi))


# ═══════════════════════════ 2. collaudo ═══════════════════════════

def prova_collaudo(tmp: Path, iso):
    print("— 2. collaudo: la candidata prima dell'approvazione")
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    P.installa(est, M1, CODICE1)
    svs = svc.sviluppi
    r, r2, lav = apri_e_avvia(ctx, est, svc, compito="Fai funzionare l'estensione del meteo "
                                                     "per qualunque città")
    n = candidata(est)
    svc.finisci(lav, "fatto", estensione={"nome": "meteo_citta", "versione": n})
    sv = svs.corrente("u1")
    verifica("prima del collaudo l'estensione attiva è ancora la versione 1, senza input",
             reg.get("est_meteo_citta") is not None
             and "citta" not in (reg.get("est_meteo_citta").parameters.get("properties") or {}))
    ctx.turno = 5
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "Bergamo"})
    testo = json.dumps(out, ensure_ascii=False)
    verifica("«prova con Bergamo»: la versione 2 gira nel container e risponde",
             "A Bergamo ci sono 18 gradi" in testo and "sviluppo_collaudo" in ctx.regole,
             testo[:300])
    verifica("il risultato dice che non è ancora attiva", "NON ancora approvata" in testo)
    out = P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "citta: Atlantide"})
    verifica("«prova una città che non esiste»: il caso «non trovato» (citta: …)",
             "Non ho trovato la città Atlantide" in json.dumps(out, ensure_ascii=False))
    verifica("i collaudi sono nello sviluppo, con l'esito",
             len(sv.collaudi) == 2 and sv.collaudi[0]["ok"] and "Bergamo" in sv.collaudi[0]["dati"]
             and "18 gradi" in sv.collaudi[0]["esito"], str(sv.collaudi))
    verifica("e sulla scheda", "## Collaudi" in svs.testo_scheda(sv)
             and "Atlantide" in svs.testo_scheda(sv))
    verifica("dopo il collaudo l'estensione attiva è ancora la 1 (niente approvata da sola)",
             est.archivio.voce("meteo_citta")["attiva"] == 1)
    verifica("sviluppo_collauda è un tool non fidato con la fonte «estensione» (busta)",
             reg.get("sviluppo_collauda").non_fidato
             and politica.fonte_di("sviluppo_collauda", reg.get("sviluppo_collauda")) == "estensione")
    # Impronta: un file della candidata cambiato dopo la consegna
    cart = est.archivio.cartella_versione("meteo_citta", n)
    (cart / "estensione.py").write_text(CODICE2 + "\n# cambiato\n", encoding="utf-8")
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "Bergamo"})
    verifica("contrario: file della candidata cambiati → non la provo (estensione_impronta)",
             "cambiati" in detta(out) and "estensione_impronta" in ctx.regole, detta(out))
    (cart / "estensione.py").write_text(CODICE2, encoding="utf-8")
    # Un familiare non collauda
    ctx.speaker_ctx = P.speaker("Bianca", "familiare")
    out = P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "Bergamo"})
    verifica("contrario: Bianca (familiare) non collauda", out.get("ok") is False
             and "Bergamo" not in json.dumps(out.get("risultati") or {}), detta(out))
    ctx.speaker_ctx = P.speaker()
    # Argomenti: forme
    m = P.valida(M2)
    verifica("dati → input: «Bergamo», «citta=Roma», oggetto JSON",
             ts._argomenti(m, "Bergamo") == {"citta": "Bergamo"}
             and ts._argomenti(m, "citta=Roma") == {"citta": "Roma"}
             and ts._argomenti(m, '{"citta": "Lodi"}') == {"citta": "Lodi"})


# ═══════════════════════════ 3. revisione e attivazione ═══════════════════════════

def prova_revisione(tmp: Path, iso):
    print("— 3. revisione, attivazione con la sfida, chiusura")
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    P.installa(est, M1, CODICE1)
    svs = svc.sviluppi
    r, r2, lav = apri_e_avvia(ctx, est, svc, compito="Fai funzionare l'estensione del meteo "
                                                     "per qualunque città")
    n = candidata(est)
    svc.finisci(lav, "fatto", estensione={"nome": "meteo_citta", "versione": n})
    sv = svs.corrente("u1")
    P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "Bergamo"}, turno=5)
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=6)
    f = detta(out)
    verifica("avanti dal collaudo: la revisione detta (permessi, analisi, test, differenze, "
             "prove)",
             sv.fase == "revisione" and f.startswith("Revisione della versione 2 di «Meteo "
                                                     "Borgoverde e Valfiorita»")
             and "Permessi:" in f and "Analisi del codice:" in f and "Test:" in f
             and "Rispetto alla versione 1" in f and "righe in più" in f and "Prove: 1" in f
             and f.endswith("Ti chiederò la frase di conferma."), f)
    verifica("…con i permessi nuovi rispetto alla versione approvata",
             "geocoding-api.open-meteo.com" in f, f)
    verifica("…mai i nomi dei file né il codice a voce", "estensione.py" not in f
             and "def esegui" not in f)
    verifica("la scheda ha il diff", "```diff" in sv.revisione and "+    citta" in sv.revisione,
             sv.revisione[-300:])
    verifica("la domanda «Vuoi attivarla?» è in sospeso verso sviluppo avanti",
             (out.get("in_sospeso") or {}).get("argomenti") == {"azione": "avanti"})
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=7)
    verifica("avanti dalla revisione: la frase di sfida per approvarla (attivazione)",
             sv.fase == "attivazione" and "ripeti" in detta(out)
             and est.archivio.voce("meteo_citta")["attiva"] == 1, detta(out))
    # La sfida superata: Brain richiama estensione_gestisci approva
    ctx.speaker_ctx.sfida_superata = True
    ctx.regole = []
    out = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "approva", "nome": "meteo_citta"},
                   turno=8)
    ctx.speaker_ctx.sfida_superata = False
    verifica("sfida superata: attiva, versione 2, e lo sviluppo si chiude (attivata)",
             est.archivio.voce("meteo_citta")["attiva"] == n and sv.stato == "chiusa"
             and sv.motivo == "attivata" and "Lo sviluppo è finito" in detta(out)
             and "sviluppo_chiuso" in ctx.regole and svs.corrente("u1") is None, detta(out))
    # Contrario: candidata con i test rossi → la revisione lo dice e non chiede di attivarla
    cfg, reg, ctx, est, svc = ambiente(tmp / "rossi", iso)
    r, r2, lav = apri_e_avvia(ctx, est, svc)
    n = candidata(est, test_passano=False)
    svc.finisci(lav, "fatto", estensione={"nome": "meteo_citta", "versione": n})
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=6)
    verifica("contrario: test rossi → «Così non si può approvare», niente domanda; prima "
             "versione", "non si può approvare" in detta(out) and "in_sospeso" not in out
             and "È la prima versione" in detta(out), detta(out))


# ═══════════════════════════ 4. ritorno all'analisi ═══════════════════════════

def prova_analisi(tmp: Path, iso):
    print("— 4. ritorno all'analisi da qualunque fase")
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    svs = svc.sviluppi
    r, r2, lav = apri_e_avvia(ctx, est, svc)
    n = candidata(est)
    svc.finisci(lav, "fatto", estensione={"nome": "meteo_citta", "versione": n})
    sv = svs.corrente("u1")
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi",
                                          "cambia": "aggiungi anche l'umidità"}, turno=6)
    off = svc.offerte.get("u1")
    nuovo = off["lavoro"] if off else None
    verifica("dal collaudo: torna all'analisi e propone la specifica nuova («Procedo?»)",
             sv.fase == "analisi" and nuovo is not None
             and detta(out).endswith("Va bene così, o la cambiamo?")
             and "Entriamo" not in detta(out)
             and "umidità" in detta(out) and sv.proposto == nuovo.id, detta(out))
    verifica("…versione nuova della stessa estensione, con i file della versione provata",
             nuovo.estensione == "meteo_citta" and "atlantide" in nuovo.file_iniziali.get(
                 "estensione.py", "") and "calliope_estensione.py" in nuovo.file_iniziali
             and "umidità" in nuovo.vincoli)
    ctx.turno = 7
    ta._delega_lavoro(ctx, proposta=nuovo.id)
    verifica("il «sì» → di nuovo allo sviluppo con il lavoro nuovo",
             sv.fase == "sviluppo" and sv.lavoro == nuovo.id)
    # Durante lo sviluppo: il lavoro in corso si ferma
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi",
                                          "cambia": "solo le città italiane"}, turno=8)
    verifica("dallo sviluppo: il lavoro in corso si ferma e lo dice",
             nuovo.id in svc.annullati and detta(out).startswith("Ho fermato il lavoro")
             and sv.fase == "analisi", detta(out))
    # Senza dire cosa cambiare: la domanda
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "analisi"}, turno=9)
    verifica("«torniamo all'analisi» senza la modifica: «cosa vuoi cambiare?» in sospeso",
             detta(out).endswith("cosa vuoi cambiare?")
             and (out.get("in_sospeso") or {}).get("tool") == "sviluppo_passo")
    verifica("la storia delle fasi è nello sviluppo",
             [x.get("a") for x in sv.storia if x.get("a")][:5]
             == ["analisi", "sviluppo", "collaudo", "analisi", "sviluppo"], str(sv.storia))


# ═══════════════════════════ 5. sviluppi nuovi bloccati ═══════════════════════════

def prova_blocco(tmp: Path, iso):
    print("— 5. niente sviluppi nuovi con uno aperto")
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    svs = svc.sviluppi
    r, r2, lav = apri_e_avvia(ctx, est, svc)
    ctx.regole = []
    ctx.turno = 4
    out = te._estensione_crea(ctx, compito="un'estensione che converte le valute",
                              nome="Valute")
    verifica("un'altra estensione: non parte, propone di sospendere (sviluppo_altro_bloccato)",
             out.get("ok") is False and "sospenda" in detta(out)
             and (out.get("in_sospeso") or {}).get("argomenti") == {"azione": "sospendi"}
             and "sviluppo_altro_bloccato" in ctx.regole and len(svc.offerte) == 0, detta(out))
    out = ta._delega_lavoro(ctx, tipo="ricerca", compito="le pompe di calore")
    verifica("una ricerca dell'agente: non parte", out.get("ok") is False
             and "sospenda" in detta(out), detta(out))
    out = ta._delega_lavoro(ctx, tipo="codice", compito="uno script che rinomina le foto")
    verifica("un programma: non parte", out.get("ok") is False and "sospenda" in detta(out))
    n = candidata(est)
    svc.finisci(lav, "fatto", estensione={"nome": "meteo_citta", "versione": n})
    out = te._estensione_crea(ctx, compito="aggiungi l'umidità", modifica="meteo_citta")
    verifica("contrario: la modifica della sua estensione passa (Procedo?)",
             "sviluppo_altro_bloccato" not in json.dumps(out) and "Procedo?" in detta(out),
             detta(out))
    # risposte alle domande dell'analisi: un'altra persona in analisi, prima del lavoro
    ctx.speaker_ctx = P.speaker("Dario")
    tmp2 = tmp / "vaga"
    cfg2, reg2, ctx2, est2, svc2 = ambiente(tmp2, iso)
    svc2.sviluppi.apri("u1", "Dario", "estensione", "il meteo")
    out = te._estensione_crea(ctx2, compito="il meteo di Bergamo e Lodi, da Open-Meteo")
    verifica("contrario: in analisi, la richiesta precisata passa (stesso sviluppo)",
             "sviluppo_altro_bloccato" not in ctx2.regole and "Va bene così" in detta(out)
             and len(svc2.sviluppi.sviluppi) == 1, detta(out))
    # dopo «sospendi» si può
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "sospendi"}, turno=10)
    verifica("«sì» alla sospensione: sospeso, lo dice e come riprenderlo",
             svs.corrente("u1") is None and "riprendiamo lo sviluppo" in detta(out), detta(out))
    out = te._estensione_crea(ctx, compito="un'estensione che converte le valute",
                              nome="Valute")
    verifica("…e l'altra estensione parte, con il suo sviluppo",
             "Va bene così" in detta(out) and svs.corrente("u1") is not None
             and svs.corrente("u1").titolo == "Valute", detta(out))


# ═══════════════════════════ 6. Brain ═══════════════════════════

def brain(tmp: Path, iso):
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    reg.register(ToolSpec("ora_attuale", "l'ora", {"type": "object", "properties": {}},
                          lambda c, **a: {"ok": True, "conferma": "Sono le 10:00."},
                          levels=frozenset({"ospite", "familiare", "amministra"})))
    b = Brain(cfg, reg, ctx)
    b.backend = Registra()
    b.conv_owner = "u1"
    b.last_turn_at = time.monotonic()
    return cfg, reg, ctx, est, svc, b


class Registra(Copione):
    def __init__(self):
        super().__init__()
        self.visti = []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        yield from super().stream(messages, tools)

    def warmup(self, messages, tools):
        return {"prompt": 10}


def chiamata(nome, argomenti):
    return [("calls", [{"id": "c0", "name": nome, "arguments": argomenti}])]


def risposta(b, frase, livello="amministra"):
    return "".join(b.stream_reply(frase, livello))


def prova_brain(tmp: Path, iso):
    print("— 6. Brain: dati del turno e riga del fuori tema")
    cfg, reg, ctx, est, svc, b = brain(tmp, iso)
    svs = svc.sviluppi
    sv = svs.apri("u1", "Dario", "estensione", "il meteo per città", titolo="Meteo per città")
    sv.specifica = "dice il meteo di una città qualunque"
    svs.passa(sv, "collaudo")
    sv.estensione, sv.versione = "meteo_citta", 2
    b.backend.risposte = [chiamata("ora_attuale", {}), [("text", "Sono le 10:00.")]]
    detto = risposta(b, "Che ore sono?")
    visti = " ".join(str(m.get("content") or "") for m in b.backend.visti[0]
                     if m.get("role") == "system")
    verifica("SVILUPPO_MSG nei dati del turno: fase, specifica, cosa fare, fuori tema",
             "Modalità sviluppo aperta" in visti and "siamo al collaudo (3 di 5)" in visti
             and "sviluppo_collauda" in visti and "dice il meteo di una città qualunque" in visti
             and "Niente sviluppi nuovi" in visti and "sviluppo_modalita" in b.last_rules,
             visti[-600:])
    verifica("fuori tema con un tool d'altro: la riga che ricorda dove eravamo, in coda",
             detto.endswith("Intanto restiamo sullo sviluppo di «Meteo per città»: siamo al "
                            "collaudo.") and "sviluppo_riga_fuori_tema" in b.last_rules
             and b.history[-1]["content"].endswith("siamo al collaudo."), detto)
    b.backend.risposte = [chiamata("ora_attuale", {}),
                          [("text", "Sono le 10:00. Intanto il Meteo per città aspetta.")]]
    detto = risposta(b, "E adesso?")
    verifica("contrario: la risposta nomina già lo sviluppo → niente riga",
             "Intanto restiamo" not in detto, detto)
    b.backend.risposte = [chiamata("ora_attuale", {}), [("text", "Sono le 10. Vuoi altro?")]]
    detto = risposta(b, "Che ore sono?")
    verifica("contrario: finisce con una domanda → niente riga (resta l'ultima cosa detta)",
             detto.endswith("Vuoi altro?"), detto)
    b.backend.risposte = [chiamata("sviluppo_passo", {"azione": "stato"}), [("text", "Ok.")]]
    detto = risposta(b, "A che punto siamo?")
    verifica("contrario: un tool dello sviluppo → niente riga; lo stato detto",
             "Intanto restiamo" not in detto and "siamo al collaudo" in detto, detto)
    b.backend.risposte = [[("text", "Ciao!")]]
    detto = risposta(b, "Ciao")
    verifica("contrario: nessun tool → niente riga del codice (la scrive il modello)",
             detto == "Ciao!", detto)
    b.cfg.llm_reti_spente = ["modalita_sviluppo"]
    b.backend.risposte = [[("text", "Va bene.")]]
    risposta(b, "Che ore sono?")
    visti = " ".join(str(m.get("content") or "") for m in b.backend.visti[-1])
    verifica("rete spenta: niente dati del turno", "Modalità sviluppo" not in visti)
    b.cfg.llm_reti_spente = []
    ctx.speaker_ctx = P.speaker("Bianca", "familiare")
    b.conv_owner = "u2"
    b.backend.risposte = [[("text", "Va bene.")]]
    risposta(b, "Che ore sono?", "familiare")
    visti = " ".join(str(m.get("content") or "") for m in b.backend.visti[-1])
    verifica("contrario: Bianca non vede lo sviluppo di Dario", "Modalità sviluppo" not in visti)


# ═══════════════════════════ 7. sospensione, ripresa, promemoria ═══════════════════════════

def prova_sospensione(tmp: Path, iso):
    print("— 7. sospensione dopo 30 minuti, ripresa, promemoria del giorno")
    cfg, reg, ctx, est, svc, b = brain(tmp, iso)
    svs = svc.sviluppi
    sv = svs.apri("u1", "Dario", "estensione", "il meteo", titolo="Meteo per città")
    svs.passa(sv, "collaudo")
    sv.ultimo = time.time() - 29 * 60
    verifica("29 minuti: ancora aperto", svs.corrente("u1") is sv)
    sv.ultimo = time.time() - 31 * 60
    verifica("31 minuti senza parlarne: sospeso", svs.corrente("u1") is None
             and sv.stato == "sospesa")
    sv2 = svs.apri("u1", "Dario", "programma", "rinomina le foto", titolo="rinomina foto")
    svs.passa(sv2, "sviluppo")
    lav = svc.nuovo("codice", "rinomina", "u1", "Dario")
    lav.stato = "in_corso"
    svc.lavori.append(lav)
    sv2.lavoro = lav.id
    sv2.ultimo = time.time() - 120 * 60
    verifica("contrario: con l'agente al lavoro non si sospende (due ore)",
             svs.corrente("u1") is sv2)
    lav.stato = "fatto"
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "riprendi", "quale": "il meteo"},
                   turno=3)
    verifica("«riprendiamo lo sviluppo del meteo»: ripreso, e quello aperto si sospende",
             sv.stato == "aperta" and sv2.stato == "sospesa"
             and detta(out).startswith("Ho sospeso «rinomina foto». Riprendiamo «Meteo per "
                                       "città»: siamo al collaudo")
             and "sviluppo_ripreso" in ctx.regole, detta(out))
    verifica("una sola aperta per persona",
             sum(1 for s in svs.sviluppi if s.persona == "u1" and s.stato == "aperta") == 1)
    # Promemoria del giorno: il primo turno di chi amministra
    svs.sospendi(sv)
    b.backend.risposte = [[("text", "Buongiorno!")]]
    detto = risposta(b, "Buongiorno Calliope")
    verifica("promemoria del giorno: gli sviluppi sospesi, in coda alla prima risposta",
             detto.startswith("Buongiorno! A proposito: hai 2 sviluppi sospesi:")
             and "sviluppo_promemoria_giorno" in b.last_rules, detto)
    b.backend.risposte = [[("text", "Ciao!")]]
    detto = risposta(b, "Ciao")
    verifica("…una volta al giorno", detto == "Ciao!", detto)
    altro = Sviluppi(cfg, tmp / "lavori", svc)
    verifica("…anche dopo un riavvio (ricordati su disco)", altro.promemoria_giorno("u1") is None)
    svs.ricordati.clear()
    ctx.speaker_ctx = P.speaker("Dario", "familiare")
    b.backend.risposte = [[("text", "Ciao!")]]
    detto = risposta(b, "Ciao", "familiare")
    verifica("contrario: Dario riconosciuto come familiare (zona grigia) → niente promemoria",
             detto == "Ciao!", detto)
    ctx.speaker_ctx = P.speaker()
    b.backend.risposte = [[("text", "Ciao, vuoi qualcosa?")]]
    detto = risposta(b, "Ciao")
    verifica("contrario: la risposta finisce con una domanda → il promemoria aspetta",
             detto.endswith("vuoi qualcosa?") and svs.promemoria_giorno("u1") is not None)
    sv.ultimo = time.time()
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "stato"}, turno=9)
    verifica("stato senza uno aperto: dice i sospesi", "sospesi" in detta(out), detta(out))


# ═══════════════════════════ 8. programma → estensione ═══════════════════════════

PROGRAMMA = "\n".join(["def calcola(a, b):"] + [f"    x{i} = a + b + {i}" for i in range(160)]
                      + ["    return a + b", "", "print(calcola(3, 5))"])


def prova_programma(tmp: Path, iso):
    print("— 8. programma: collaudo, revisione, proposta di farne un'estensione")
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    svs = svc.sviluppi
    ctx.turno = 1
    out = ta._delega_lavoro(ctx, tipo="codice", compito="un programma che somma due numeri")
    sv = svs.corrente("u1")
    verifica("lavoro_affida di codice di chi amministra apre lo sviluppo di un programma",
             sv is not None and sv.tipo == "programma" and sv.proposto == "L1"
             and detta(out).startswith("Entriamo in modalità sviluppo per il programma")
             and "Va bene così" in detta(out), detta(out))
    ctx.turno = 2
    ta._delega_lavoro(ctx, proposta="L1")
    lav = svc.lavori[-1]
    cartella = tmp / "risultati" / "L1"
    cartella.mkdir(parents=True)
    (cartella / "somma.py").write_text(PROGRAMMA, encoding="utf-8")
    (cartella / "test_somma.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    (cartella / "lavoro.json").write_text(json.dumps({"test": {"eseguiti": 3, "falliti": 0}}),
                                          encoding="utf-8")
    item = svc.finisci(lav, "fatto", cartella=str(cartella), test={"eseguiti": 3, "falliti": 0})
    verifica("programma finito: collaudo, «provalo con…»",
             sv.fase == "collaudo" and item["messaggio"].endswith("Con cosa provo?"),
             item["messaggio"])
    out = P.chiama(reg, ctx, "sviluppo_collauda", {"dati": "3 e 5"}, turno=4)
    verifica("collaudo del programma: programma_esegui con i dati",
             svc.esecuzioni.eseguiti == [("L1", ["3", "5"])] and "stampa 8" in detta(out)
             and len(sv.collaudi) == 1, detta(out))
    verifica("misura del programma: righe senza i test",
             misura_programma(cartella)["righe"] >= 160
             and misura_programma(cartella)["file"] == 1)
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=5)
    f = detta(out)
    verifica("revisione di un programma grande: la proposta di un'estensione, con la differenza",
             sv.fase == "revisione" and "vuoi che diventi un'estensione?" in f
             and "si esegue adesso e basta" in f and "la richiami a voce" in f
             and (out.get("in_sospeso") or {}).get("argomenti") == {"azione": "promuovi"}, f)
    ctx.regole = []
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "promuovi"}, turno=6)
    nuovo = svs.corrente("u1")
    verifica("promuovi: chiuso il programma, aperto lo sviluppo dell'estensione (Procedo?)",
             sv.stato == "chiusa" and sv.motivo == "diventa estensione" and nuovo is not None
             and nuovo.tipo == "estensione" and "Va bene così" in detta(out), detta(out))
    off = svc.offerte["u1"]["lavoro"]
    verifica("…con i file del programma per l'agente (programma/), test compresi",
             "programma/somma.py" in off.file_iniziali and "programma/test_somma.py"
             in off.file_iniziali and "programma/" in off.vincoli, str(list(off.file_iniziali)))
    # Programma piccolo: niente proposta
    cfg, reg, ctx, est, svc = ambiente(tmp / "piccolo", iso)
    svs = svc.sviluppi
    sv = svs.apri("u1", "Dario", "programma", "somma", titolo="somma")
    piccolo = tmp / "piccolo" / "ris"
    piccolo.mkdir(parents=True)
    (piccolo / "somma.py").write_text("print(3 + 5)\n", encoding="utf-8")
    sv.cartella = str(piccolo)
    svs.passa(sv, "collaudo")
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=3)
    verifica("contrario: programma piccolo → «Va bene così?», niente proposta",
             detta(out).endswith("Va bene così?") and "estensione" not in detta(out), detta(out))
    out = P.chiama(reg, ctx, "sviluppo_passo", {"azione": "avanti"}, turno=4)
    verifica("avanti dalla revisione di un programma: chiuso (consegnato)",
             sv.stato == "chiusa" and sv.motivo == "consegnato" and "cartella Lavori" in detta(out))


# ═══════════════════════════ 9. politica ═══════════════════════════

def turno_dato(testo, persona="u1"):
    return politica.Turno(testo=testo, contaminazione=frozenset({"agente"}), persona=persona,
                          esterni=[("agente", "ho preparato l'estensione Meteo per città")])


def prova_politica(tmp: Path, iso):
    print("— 9. politica: passi interni senza «C'è di mezzo…»")
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    # La politica di prima (per tornare indietro con una riga); la politica per valore, accesa
    # dal 09/10, alla fine
    cfg.politica_per_valore = False
    P.installa(est, M1, CODICE1)
    P.installa(est, P.manifesto("valute", "Valute", "Converte le valute."), CODICE1)
    svs = svc.sviluppi
    r, r2, lav = apri_e_avvia(ctx, est, svc)
    n = candidata(est)
    svc.finisci(lav, "fatto", estensione={"nome": "meteo_citta", "versione": n})

    def decide(nome, args, testo="va bene, andiamo avanti", sc=None):
        ctx.speaker_ctx = sc or P.speaker()
        ctx.politica = turno_dato(testo)
        ctx.regole = []
        try:
            res = politica.controlla(reg.get(nome), nome, args, ctx)
        finally:
            ctx.politica = None
        return res, list(ctx.regole)

    res, reg_ = decide("sviluppo_passo", {"azione": "avanti"})
    verifica("sviluppo avanti con il lavoro dell'agente di mezzo: esegue (sviluppo_intento)",
             res is None and "sviluppo_intento" in reg_, str(res))
    res, reg_ = decide("sviluppo_collauda", {"dati": "Bergamo"}, "prova con Bergamo")
    verifica("sviluppo_collauda: esegue", res is None)
    res, reg_ = decide("estensione_gestisci", {"azione": "approva", "nome": "meteo_citta"},
                       "attivala")
    verifica("approvare la sua estensione: niente domanda della politica (la sfida resta "
             "nel servizio)", res is None and "sviluppo_intento" in reg_, str(res))
    ctx.speaker_ctx, ctx.regole = P.speaker(), []
    args = reg.get("estensione_gestisci").prepara(ctx, {"azione": "approva", "nome": "MeteoSì"})
    verifica("approva con il nome dato alla richiesta («MeteoSì»): è l'estensione dello "
             "sviluppo (sviluppo_nome_estensione)",
             args.get("nome") == "meteo_citta" and "sviluppo_nome_estensione" in ctx.regole,
             str(args))
    args = reg.get("estensione_gestisci").prepara(ctx, {"azione": "approva", "nome": "valute"})
    verifica("contrario: il nome di un'altra estensione che c'è resta quello",
             args.get("nome") == "valute")
    res, reg_ = decide("sviluppo_apri", {"compito": "aggiungi l'umidità",
                                           "modifica": "meteo_citta"}, "aggiungi l'umidità")
    verifica("modifica della sua estensione: esegue", res is None, str(res))
    # contrari
    res, _ = decide("estensione_gestisci", {"azione": "approva", "nome": "valute"}, "attivala")
    verifica("contrario: approvare un'ALTRA estensione → la domanda di sempre",
             res is not None and "C'è di mezzo" in detta(res), str(res))
    res, reg_ = decide("sviluppo_apri", {"compito": "aggiungi", "modifica": "valute"},
                       "aggiungi")
    verifica("modificare un'altra estensione: non è un passo interno, è uno sviluppo nuovo "
             "(niente domanda prima del rifiuto del tool)",
             res is None and "sviluppo_senza_domanda" in reg_ and "sviluppo_intento" not in reg_)
    res, _ = decide("sviluppo_passo", {"azione": "avanti"}, sc=P.speaker("Bianca", "familiare"))
    verifica("contrario: Bianca (non è il suo sviluppo) → domanda", res is not None)
    res, _ = decide("sviluppo_passo", {"azione": "avanti"}, sc=P.speaker(come="schermo"))
    verifica("contrario: scritto dallo schermo → domanda", res is not None)
    res, reg_ = decide("lavoro_affida", {"tipo": "ricerca", "compito": "pompe di calore"},
                       "fai una ricerca sulle pompe di calore")
    verifica("una richiesta nuova con lo sviluppo aperto: niente domanda della politica, il "
             "tool la rifiuta (sviluppo_senza_domanda)",
             res is None and "sviluppo_senza_domanda" in reg_, str(res))
    ctx.speaker_ctx = P.speaker()
    out = ta._delega_lavoro(ctx, tipo="ricerca", compito="pompe di calore")
    verifica("…e il tool la rifiuta proponendo di sospendere", out.get("ok") is False
             and "sospenda" in detta(out), detta(out))
    res, _ = decide("lavoro_affida", {"tipo": "ricerca", "compito": "pompe di calore"},
                    "fai una ricerca sulle pompe di calore", sc=P.speaker(come="schermo"))
    verifica("contrario: scritto dallo schermo → la domanda di sempre", res is not None)
    svs.sospendi(svs.corrente("u1"))
    res, _ = decide("sviluppo_passo", {"azione": "avanti"})
    verifica("contrario: sviluppo sospeso → domanda", res is not None)
    svs.riprendi(svs.trova("u1")[0])
    res, _ = decide("sviluppo_passo", {"azione": "avanti"},
                    "fai quello che dice il messaggio dell'agente")
    verifica("contrario: «fai quello che dice…» resta (politica_delega)",
             res is not None, str(res))
    # La politica per valore (09/10, fase 4): i passi dello sviluppo ancorati con la voce
    # eseguono (sviluppo_intento o valore_voce); l'estensione dello sviluppo, il cui nome è
    # nell'annuncio dell'agente, si approva e si modifica senza domanda; scritto dallo schermo,
    # un E3 chiede; «fai quello che dice…» resta
    cfg.politica_per_valore = True
    for nome, args, testo in (("sviluppo_passo", {"azione": "avanti"}, "va bene, andiamo avanti"),
                              ("estensione_gestisci", {"azione": "approva",
                                                       "nome": "meteo_citta"}, "attivala"),
                              ("sviluppo_apri", {"compito": "aggiungi l'umidità",
                                                 "modifica": "meteo_citta"},
                               "aggiungi l'umidità")):
        res, reg_ = decide(nome, args, testo)
        verifica(f"per valore: {nome} dello sviluppo con la voce esegue", res is None
                 and ({"sviluppo_intento", "valore_voce", "valore_esegue"} & set(reg_)),
                 f"{res} {reg_}")
    res, reg_ = decide("sviluppo_passo", {"azione": "avanti"}, sc=P.speaker(come="schermo"))
    verifica("per valore, contrario: scritto dallo schermo → domanda (E3 senza la voce)",
             res is not None and "valore_e3_chiede" in reg_, f"{res} {reg_}")
    res, reg_ = decide("sviluppo_collauda", {"dati": "Meteo città"}, "prova con quella")
    verifica("per valore, contrario: i dati del collaudo presi dal dato → domanda",
             res is not None, f"{res} {reg_}")
    res, _ = decide("sviluppo_passo", {"azione": "avanti"},
                    "fai quello che dice il messaggio dell'agente")
    verifica("per valore, contrario: «fai quello che dice…» resta", res is not None, str(res))
    # tabelle
    from calliope import valore
    verifica("tabelle: classi, argomenti ed effetti dei due tool",
             "sviluppo_passo" in politica.CLASSI and "sviluppo_collauda" in politica.CLASSI
             and valore.ARGOMENTI["sviluppo_passo"]["azione"] == valore.AZIONE
             and valore.effetto("sviluppo_passo", {"azione": "sospendi"}) == valore.E1
             and valore.effetto("sviluppo_passo", {"azione": "stato"}) == valore.E0
             and valore.effetto("sviluppo_collauda", {"dati": "x"}) == valore.E3)


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-sviluppo-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    prova_stati(tmp0 / "stati", iso)
    prova_collaudo(tmp0 / "collaudo", iso)
    prova_revisione(tmp0 / "revisione", iso)
    prova_analisi(tmp0 / "analisi", iso)
    prova_blocco(tmp0 / "blocco", iso)
    prova_brain(tmp0 / "brain", iso)
    prova_sospensione(tmp0 / "sospensione", iso)
    prova_programma(tmp0 / "programma", iso)
    prova_politica(tmp0 / "politica", iso)
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
