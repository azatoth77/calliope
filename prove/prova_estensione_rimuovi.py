"""L'eliminazione definitiva di un'estensione (09/10/2026, decisione di Dario; a secco).

Sulla DGX ci sono due estensioni del meteo che a voce si dicono uguali: una disattivata e una
attiva, rinominata dalla persona. Fino al 09/10 «rimuovi l'estensione Meteo città» sceglieva
l'attiva. Qui, con nomi di fantasia («Meteo città» disattivata, «Meteocittà» attiva):

1. per «rimuovi» (ed «elimina», «cancella», «togli») si sceglie la disattivata; tra due nello
   stesso stato quella detta proprio così; contrari: usarla, disattivarla → l'attiva;
2. la domanda dice quale (titolo, stato, versione, cosa fa), l'omonima che resta, e che è
   definitiva; il «sì» in un turno dopo elimina quella, l'altra resta attiva col suo tool;
3. un'attiva non si elimina: «prima la disattivo?» (in sospeso «disattiva»); uno sviluppo
   aperto o sospeso, o un lavoro dell'agente in corso, la bloccano con una frase chiara;
4. dopo: indice (anche riletto dal disco), tool `est_`, permessi «sempre», elenco, partite
   dei giochi e schede che rimandano a lei (sviluppo, lavoro) nella cronologia degli schermi,
   in memoria e su disco; le schede d'altro restano;
5. la cartella con le versioni approvate in sola lettura (file e cartelle) si cancella tutta,
   anche con i permessi di Linux (cartelle r-x).

    python prove\\prova_estensione_rimuovi.py
"""

import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from calliope.estensioni.archivio import Archivio, _sola_lettura, _togli_cartella  # noqa: E402

# Le prove 1–4 (servizio, tool, sviluppi) importano tutto Calliope: si caricano in main, così
# la 5 gira anche da sola su Linux con la sola libreria standard (`--solo-file`)
P = S = _nome = preferenza = None


def _carica():
    global P, S, _nome, preferenza
    import prova_estensioni
    import prova_sviluppo
    from calliope.estensioni.servizio import _nome as n, preferenza as pr
    P, S, _nome, preferenza = prova_estensioni, prova_sviluppo, n, pr

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                                 else ""), flush=True)


def detta(r) -> str:
    return str(r.get("risposta_finale") or r.get("errore") or "")


INPUT = {"type": "object", "properties": {"citta": {
    "type": "string", "description": "nome della città"}}, "required": ["citta"]}


def manifesto(nome, titolo, descr):
    return {"nome": nome, "titolo": titolo, "descrizione": descr, "input": INPUT,
            "permessi": {}, "livello": "familiare", "limiti": {"tempo_s": 5, "memoria_mb": 128}}


M_VECCHIA = manifesto("meteo_citta", "Meteo città", "Dice il meteo di una città.")
M_COD = manifesto("meteo_codificato", "Meteo città codificata",
                  "Dice il meteo di una città, con il nome codificato.")


def ambiente(tmp, iso):
    cfg, reg, ctx, est, svc = S.ambiente(tmp, iso)
    P.installa(est, M_VECCHIA, S.CODICE2)
    est.archivio.disattiva("meteo_citta")
    P.installa(est, M_COD, S.CODICE2)
    est.archivio.rinomina("meteo_codificato", "Meteocittà")
    est.aggiorna_tool()
    return cfg, reg, ctx, est, svc


# ═══════════════════════════ 1. quale si elimina ═══════════════════════════

def prova_scelta(tmp, iso):
    print("— 1. «rimuovi» sceglie la disattivata")
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    a = est.archivio
    for azione in ("rimuovi", "elimina", "cancella", "togli"):
        verifica(f"«{azione} l'estensione Meteo città» → la disattivata",
                 _nome("Meteo città", a, preferenza(azione)) == "meteo_citta")
    verifica("…anche detta attaccata, «Meteocittà»",
             _nome("Meteocittà", a, preferenza("rimuovi")) == "meteo_citta")
    verifica("contrario: per usarla o disattivarla, l'attiva",
             _nome("Meteo città", a, preferenza("disattiva")) == "meteo_codificato"
             and _nome("Meteo città", a) == "meteo_codificato")
    verifica("contrario: con il nome interno, sempre quella",
             _nome("meteo_codificato", a, preferenza("rimuovi")) == "meteo_codificato")
    a.disattiva("meteo_codificato")
    verifica("tutte e due disattivate: quella detta proprio così",
             _nome("Meteocittà", a, preferenza("rimuovi")) == "meteo_codificato"
             and _nome("Meteo città", a, preferenza("rimuovi")) == "meteo_citta")


# ═══════════════════════════ 2. domanda e «sì» ═══════════════════════════

def prova_domanda(tmp, iso):
    print("— 2. la domanda dice quale, il «sì» elimina quella")
    cfg, reg, ctx, est, svc = ambiente(tmp, iso)
    a = est.archivio
    a.concedi_sempre("meteo_citta", "u1", "rete_pubblica", "api.esempio.it")
    hub = S_hub(tmp / "schede")
    ctx.schermi = hub
    # Le schede: lo sviluppo chiuso di prima e il lavoro dell'agente (rimandano a lei), più
    # una lista che non c'entra
    sv = svc.sviluppi.apri("u1", "Dario", "estensione", "il meteo", titolo="Meteo città",
                           estensione="meteo_citta")
    svc.sviluppi.chiudi(sv, "attivata")
    from calliope.schermi.hub import Mittente
    dario = Mittente("u1", "Dario", "amministra", True)
    for c in ({"tipo": "sviluppo", "chiave": f"sviluppo:{sv.id}", "titolo": "Sviluppo",
               "visibilita": "personale", "sviluppo": {"id": sv.id, "nome": "meteo_citta"}},
              {"tipo": "lavoro", "chiave": "lavoro:L7", "titolo": "Lavoro",
               "visibilita": "personale"},
              {"tipo": "lista", "chiave": "lista:spesa", "titolo": "Spesa",
               "visibilita": "personale"}):
        hub.cronologia.aggiungi("u1", c)
        hub.ricorda(c, dario)
    svc.lavori.append(SimpleNamespace(id="L7", estensione="meteo_citta", stato="fatto",
                                      persona="u1"))
    # Una partita del gioco (finta) da chiudere
    giochi = Giochi_finti()
    est.giochi = giochi

    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "rimuovi", "nome": "Meteo città"},
                 turno=3)
    d = detta(r)
    verifica("la domanda: titolo, stato, versione, cosa fa, l'omonima che resta, definitiva",
             d == "Elimino per sempre «Meteo città» (disattivata, versione 1): dice il meteo "
                  "di una città. «Meteocittà», attiva, resta com'è. Cancello i file di tutte "
                  "le versioni e i suoi dati: non si torna indietro. Procedo?", d)
    sosp = r.get("in_sospeso") or {}
    verifica("…in sospeso il nome interno della disattivata",
             sosp.get("argomenti") == {"azione": "rimuovi", "nome": "meteo_citta"}, str(sosp))
    verifica("…e niente è ancora eliminato", a.voce("meteo_citta") is not None
             and (a.cartella / "meteo_citta").exists())
    r = P.chiama(reg, ctx, "estensione_gestisci", sosp["argomenti"], turno=3)
    verifica("contrario: mai nella stessa risposta", a.voce("meteo_citta") is not None)
    r = P.chiama(reg, ctx, "estensione_gestisci", sosp["argomenti"], turno=4)
    verifica("il «sì» dopo: eliminata", detta(r) == "Fatto: «Meteo città» è eliminata, con "
             "tutte le sue versioni e i suoi dati.", detta(r))
    verifica("…indice, cartella e permessi «sempre» (anche riletti dal disco)",
             a.voce("meteo_citta") is None and not (a.cartella / "meteo_citta").exists()
             and Archivio(a.cartella).voce("meteo_citta") is None
             and not a.sempre("meteo_citta", "u1", "rete_pubblica", "api.esempio.it"))
    verifica("…l'omonima attiva resta, col suo tool",
             a.voce("meteo_codificato")["stato"] == "attiva"
             and reg.get("est_meteo_codificato") is not None
             and reg.get("est_meteo_citta") is None)
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "elenca"}, turno=5)
    verifica("…l'elenco non la dice più", detta(r) == "Ho un'estensione: «Meteocittà» "
             "(attiva).", detta(r))
    restano = [v["scheda"]["chiave"] for v in hub.cronologia.ultime("u1")]
    verifica("…le schede che rimandavano a lei escono dalla cronologia su disco, le altre "
             "restano", restano == ["lista:spesa"], str(restano))
    hub.cronologia._dati.clear()
    restano = [v["scheda"]["chiave"] for v in hub.cronologia.ultime("u1")]
    verifica("…anche rilette dal file", restano == ["lista:spesa"], str(restano))
    verifica("…e dall'ultima scheda della persona", (hub.ultima(dario) or {}).get("chiave")
             == "lista:spesa", str(hub.ultima(dario)))
    verifica("…le partite del gioco chiuse", giochi.chiuse == ["meteo_citta"])
    righe = (a.cartella / "decisioni.jsonl").read_text(encoding="utf-8").splitlines()
    ultima = json.loads(righe[-1])
    verifica("…e il registro delle decisioni lo dice", ultima.get("esito") == "eliminata"
             and ultima.get("estensione") == "meteo_citta", righe[-1])


class Giochi_finti:
    def __init__(self):
        self.chiuse = []

    def chiudi_di(self, nome):
        self.chiuse.append(nome)
        return ["P1"]


def S_hub(cartella):
    from calliope.config import Config
    from calliope.schermi.archivio import ArchivioSchermi
    from calliope.schermi.cronologia import CronologiaSchede
    from calliope.schermi.hub import Schermi
    cfg = Config()
    cfg.config_dir = str(cartella)
    Path(cartella).mkdir(parents=True, exist_ok=True)
    hub = Schermi(cfg, ArchivioSchermi(str(Path(cartella) / "schermi.db")), log=lambda m: None)
    hub.cronologia = CronologiaSchede(Path(cartella) / "cron", log=lambda m: None,
                                      scrivi_subito=True)
    return hub


# ═══════════════════════════ 3. quando non si può ═══════════════════════════

def prova_blocchi(tmp, iso):
    print("— 3. un'attiva, uno sviluppo aperto, un lavoro in corso")
    cfg, reg, ctx, est, svc = ambiente(tmp / "a", iso)
    a = est.archivio
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "rimuovi",
                                                   "nome": "meteo_codificato"}, turno=2)
    verifica("un'attiva: niente eliminato, prima la disattiva (in sospeso «disattiva»)",
             detta(r) == "«Meteocittà» è attiva, versione 1: prima la disattivo? Poi, se vuoi, "
                         "la posso eliminare."
             and (r.get("in_sospeso") or {}).get("argomenti") == {"azione": "disattiva",
                                                                  "nome": "meteo_codificato"}
             and "estensione_rimuovi_attiva" in ctx.regole
             and a.voce("meteo_codificato")["stato"] == "attiva", detta(r))
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "rimuovi",
                                                   "nome": "meteo_codificato"}, turno=3)
    verifica("…e un secondo «rimuovi» non la elimina lo stesso",
             a.voce("meteo_codificato") is not None and reg.get("est_meteo_codificato"))

    sv = svc.sviluppi.apri("u1", "Dario", "estensione", "i giorni", titolo="Meteo città",
                           estensione="meteo_citta")
    ctx.regole.clear()
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "rimuovi", "nome": "Meteo città"},
                 turno=4)
    verifica("uno sviluppo aperto su di lei la blocca, con la frase",
             detta(r) == f"Non posso eliminare «Meteo città»: c'è uno sviluppo aperto su di "
                         f"lei ({sv.id}). Prima chiudilo, poi la posso eliminare."
             and "estensione_rimuovi_occupata" in ctx.regole
             and a.voce("meteo_citta") is not None, detta(r))
    svc.sviluppi.sospendi(sv)
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "rimuovi", "nome": "Meteo città"},
                 turno=5)
    verifica("…anche sospeso", "sviluppo sospeso" in detta(r), detta(r))
    svc.sviluppi.chiudi(sv, "chiesto")
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "rimuovi", "nome": "Meteo città"},
                 turno=6)
    verifica("…chiuso, si può (la domanda)", detta(r).endswith("Procedo?"), detta(r))

    cfg, reg, ctx, est, svc = ambiente(tmp / "b", iso)
    svc.lavori.append(SimpleNamespace(id="L9", estensione="meteo_citta", stato="in_corso",
                                      persona="u1"))
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "rimuovi", "nome": "Meteo città"},
                 turno=2)
    verifica("un lavoro dell'agente in corso su di lei la blocca",
             detta(r) == "Non posso eliminare «Meteo città»: un agente ci sta lavorando (L9). "
                         "Aspetta che finisca, o annulla il lavoro, poi la posso eliminare.",
             detta(r))
    svc.lavori[-1].stato = "fatto"
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "rimuovi", "nome": "Meteo città"},
                 turno=3)
    verifica("…finito, si può", detta(r).endswith("Procedo?"), detta(r))
    ctx.speaker_ctx = P.speaker("Bianca", "familiare")
    r = P.chiama(reg, ctx, "estensione_gestisci", {"azione": "rimuovi", "nome": "meteo_citta"},
                 turno=4)
    verifica("contrario: un familiare non elimina (nemmeno col «sì» al turno dopo)",
             "solo chi amministra" in detta(r)
             and est.archivio.voce("meteo_citta") is not None, detta(r))


# ═══════════════════════════ 4. i giochi ═══════════════════════════

def prova_giochi():
    print("— 4. le partite di un gioco eliminato")
    from calliope.schermi.giochi import Giochi, Partita
    from calliope.schermi.hub import Mittente
    g = Giochi(SimpleNamespace(), hub=None)
    m = {"titolo": "Tris", "scheda": {}}
    mitt = Mittente("u1", "Dario", "amministra", True)
    p1, p2 = Partita("tris", 1, m, mitt), Partita("dama", 1, m, mitt)
    for p in (p1, p2):
        g.partite[p.id] = p
        g._per_gettone[p.gettone] = p.id
    tolte = g.chiudi_di("tris")
    verifica("chiude le sue (gettone compreso), le altre restano",
             tolte == [p1.id] and p1.id not in g.partite and p1.gettone not in g._per_gettone
             and p2.id in g.partite)


# ═══════════════════════════ 5. sola lettura ═══════════════════════════

def prova_sola_lettura(tmp):
    print("— 5. la cartella in sola lettura si cancella tutta")
    radice = tmp / "est" / "gioco"
    for rel in ("v1/estensione.py", "v1/esempi/pagina.html", "v1/esempi/sotto/dati.json",
                "v2/estensione.py", "dati/gioco_punti.json"):
        f = radice / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x", encoding="utf-8")
    _sola_lettura(radice / "v1")
    _sola_lettura(radice / "v2")
    # Come una cancellazione a mano: su Linux senza scrivere nella cartella non si toglie
    bloccato = False
    try:
        (radice / "v1" / "estensione.py").unlink()
    except OSError:
        bloccato = True
    verifica("la versione approvata è davvero in sola lettura", bloccato
             or (os.name != "nt" and os.geteuid() == 0))
    _togli_cartella(radice)
    verifica("_togli_cartella la toglie tutta (file e cartelle in sola lettura)",
             not radice.exists())
    _togli_cartella(radice)
    verifica("…e su una cartella che non c'è non fa niente", not radice.exists())
    # Un archivio vero: approvata, poi rimossa
    a = Archivio(tmp / "arch")
    n = a.nuova_candidata(dict(M_VECCHIA), {"estensione.py": b"x = 1\n",
                                                 "esempi/a.html": b"<p>a</p>"}, "Dario")
    a.approva("meteo_citta", n, "Dario")
    st = os.stat(a.cartella_versione("meteo_citta", n) / "estensione.py").st_mode
    verifica("approvata: file senza scrittura", not st & stat.S_IWUSR or os.name == "nt")
    a.rimuovi("meteo_citta")
    verifica("Archivio.rimuovi: cartella e voce via",
             not (a.cartella / "meteo_citta").exists() and a.voce("meteo_citta") is None)


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-rimuovi-"))
    if len(sys.argv) > 1 and sys.argv[1] == "--solo-file":
        # Solo la parte 5 (per provarla su Linux senza le dipendenze delle altre)
        prova_sola_lettura(tmp0)
    else:
        _carica()
        os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
        os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
        os.environ["DOCKER_FINTO_MODO"] = "ok"
        iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
        prova_scelta(tmp0 / "scelta", iso)
        prova_domanda(tmp0 / "domanda", iso)
        prova_blocchi(tmp0 / "blocchi", iso)
        prova_giochi()
        prova_sola_lettura(tmp0 / "file")
    try:
        _togli_cartella(tmp0)
    except OSError:                 # su Windows i database delle prove restano aperti
        pass
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
