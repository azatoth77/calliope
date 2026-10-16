import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # prova_voci_famiglia

"""Prova a secco della conservazione dei dati (12/10/2026, calliope/conserva.py, decisione 0028 T1;
dal 16/10 la decisione 0031: i minori di casa come gli adulti, issue #104).

- `decidi`, il solo posto: persona di casa riconosciuta sì, **minore compreso** (testo, eventi,
  conversazioni); ospite e zona grigia no (testo); nel dubbio tra un adulto e un minore il testo
  sì e la voce no; la voce solo sopra soglia, senza compagnia, con il consenso (chi amministra sì
  finché non dice no, gli altri adulti solo dopo il loro «sì», un minore solo col «sì» di un
  tutore), mai con `conserva_voce: false`;
- registro dei turni: le parole restano per adulti e minori (dal profilo o dalla fascia) e nel
  dubbio con un minore; ospiti e zona grigia senza parole (restano i numeri e quante parole);
- voce: μ-law che si rilegge (errore piccolo), un file per frase nella cartella della persona,
  permessi 600/700 fuori da Windows; mai per ospite, adulto senza consenso, minore senza il sì di
  un tutore, scritto, frase ignorata, compagnia, dubbio con un minore, frase di sfida, codice
  detto; il minore col sì del tutore sì;
- consenso: il «sì» salvato nel profilo (per un minore con il tutore che l'ha dato); la revoca
  cancella le registrazioni;
- rotazione: giorni vecchi, persone senza più il diritto, tetto di spazio; il minore col sì del
  tutore resta;
- il registro dei turni di prima ripulito una volta (segno nella cartella): le parole del minore
  restano, quelle dell'ospite no;
- svuotare: una persona (voce, parole nei turni, eventi) e tutto;
- eventi: i registri di adulti e minori su disco e ripresi dopo un riavvio; quelli degli ospiti
  no, e la rotazione li toglie; le parole di un turno incerto restano solo in memoria
  (`senza_parole`); `dati_del_turno` su disco con nomi e lunghezze;
- il tool `dati_conservati`: ospite, scritto, zona grigia rifiutati; domanda e «sì»; revoca; il
  minore che dà o revoca da solo il consenso rifiutato, il tutore che lo dà con la persona e il
  «sì», un adulto non tutore rifiutato; «svuota» solo per chi amministra, con la domanda;
- da terminale: `python -m calliope.conserva` (conteggi) e `--svuota --persona` (anche di un
  minore: turni, eventi, conversazioni, voce);
- l'archivio delle conversazioni (12/10 sera): su disco l'adulto e il minore, ospite e turno
  incerto no (l'ospite nella sessione in memoria), conversazione in corso salvata, rotazione delle
  righe di prima (il minore resta), tenuta di `turn_log_days`, svuota e conteggi.

Nomi di fantasia. Tutto in una cartella temporanea. ~1 s.
"""

import datetime
import json
import shutil
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from calliope import conserva as C
from calliope.config import Config
from calliope.eventi.registro import Disco, Registri
from calliope.eventi.tipi import CAMPI_TESTO, TIPI, Evento, per_disco, senza_parole
from calliope.speaker_id import UserProfile
from calliope.tools.conserva import _dati_conservati, conserva_specs
from calliope.turnlog import TurnLog

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    print(("OK  " if ok else "ERR ") + nome + ("" if ok else f"  → {dettaglio}"))
    if not ok:
        errori += 1


class Registro:
    """I profili, come SpeakerRegistry, senza modelli."""

    def __init__(self, *profili):
        self.users = {p.name: p for p in profili}
        self.salvato = 0

    def get(self, nome):
        return self.users.get(nome)

    def by_id(self, pid):
        return next((u for u in self.users.values() if u.id == pid), None)

    def find(self, nome):
        return next((n for n in self.users if n.lower() == str(nome).lower()), None)

    def save(self):
        self.salvato += 1


def profili():
    oggi = datetime.date.today()
    amm = UserProfile(name="Primo", admin=True, id="p-amm")
    adulto = UserProfile(name="Ginevra", id="p-adu")
    minore = UserProfile(name="Leo", id="p-min",
                         nascita=f"{oggi.year - 10}-01-15", tutori=["p-amm"])
    return amm, adulto, minore


tmp = Path(tempfile.mkdtemp(prefix="calliope-conserva-"))
try:
    amm, adulto, minore = profili()
    reg = Registro(amm, adulto, minore)

    # ───────── decidi ─────────
    verifica("adulto dalla voce: testo sì", C.decidi(adulto, "testo", "voce").ok)
    verifica("adulto, frase breve: testo sì", C.decidi(adulto, "testo", "breve").ok)
    # Dal 16/10 (decisione 0031) il minore di casa come un adulto
    verifica("minore: testo, eventi e conversazioni sì (16/10, decisione 0031)",
             all(C.decidi(minore, c, "voce").ok for c in ("testo", "eventi", "conversazioni"))
             and C.decidi(minore, "testo", "voce").motivo == "minore")
    # La voce del minore (16/10, decisione 0031 aggiornata): il consenso è dei tutori e
    # implicito nella registrazione; un minore con i tutori nel profilo ce l'ha senza domanda
    verifica("minore già registrato con i tutori: voce sì senza domanda (consenso implicito)",
             minore.voce_conservata is None and C.decidi(minore, "voce", "voce", registry=reg).ok)
    minore.voce_conservata, minore.voce_conservata_da = False, "p-amm"
    verifica("minore, contrario: revocato da un tutore → voce no",
             C.decidi(minore, "voce", "voce", registry=reg).motivo == "senza_consenso")
    minore.voce_conservata, minore.voce_conservata_da = True, "p-amm"
    verifica("minore col «sì» del tutore, contrario: in compagnia o con una frase breve no",
             not C.decidi(minore, "voce", "voce", {"compagnia"}, registry=reg)
             and not C.decidi(minore, "voce", "breve", registry=reg))
    # Il tutore che l'ha dato non lo è più, o il suo profilo non c'è: senza altri tutori validi no
    orfano = UserProfile(name="Teo", id="p-teo", nascita=minore.nascita, tutori=["p-via"],
                         voce_conservata=True, voce_conservata_da="p-via")
    verifica("contrario: il consenso di un tutore il cui profilo non c'è più non vale",
             not C.consenso_voce(orfano, reg))
    orfano.tutori, orfano.voce_conservata_da = ["p-amm"], "p-adu"
    verifica("…chi l'ha dato non è (più) tutore: vale solo il consenso implicito dei tutori "
             "validi", C.consenso_voce(orfano, reg))
    orfano.tutori = []
    verifica("contrario: chi l'ha dato non è tutore e nessun tutore nel profilo: no",
             not C.consenso_voce(orfano, reg))
    verifica("contrario: un minore senza tutori nel profilo e senza un «sì»: no",
             not C.consenso_voce(UserProfile(name="Ada", id="p-ada", nascita=minore.nascita),
                                 reg))
    minore.voce_conservata = minore.voce_conservata_da = None
    # Il testo della stanza (14/10, decisione 0029 punto 5): con la tenuta accesa anche i minori
    # riconosciuti dalla voce (prove/prova_stanza_tenuta.py)
    verifica("la stanza sì anche per il minore con la voce, no nella zona grigia",
             C.decidi(minore, "stanza", "voce").ok
             and not C.decidi(minore, "stanza", "conversazione"))
    verifica("contrario: ospite, mai", not any(C.decidi(None, c, "voce") for c in C.COSE))
    verifica("dubbio con un minore (incerta, minore_vicino, minore_incerto): il testo sì",
             all(C.decidi(amm, "testo", "conversazione", {d}).ok for d in C.DUBBI_MINORE)
             and C.decidi(minore, "testo", "conversazione", {"incerta"}).ok)
    verifica("dubbio con un minore, contrario: la voce no",
             all(C.decidi(amm, "voce", "voce", {d}).motivo == "dubbio_minore"
                 for d in C.DUBBI_MINORE))
    verifica("proprietario incerto con un minore: il testo sì, la voce no",
             C.decidi(amm, "testo", "proprietario").ok
             and C.decidi(amm, "voce", "proprietario").motivo == "voce_incerta")
    verifica("contrario: zona grigia («conversazione») e nessun modo: testo no",
             not C.decidi(amm, "testo", "conversazione")
             and not C.decidi(minore, "testo", "conversazione")
             and not C.decidi(amm, "testo", None))
    verifica("chi amministra: voce sì senza averlo detto (scelta di partenza)",
             C.decidi(amm, "voce", "voce").ok)
    verifica("contrario: adulto senza consenso: voce no",
             C.decidi(adulto, "voce", "voce").motivo == "senza_consenso")
    adulto.voce_conservata = True
    verifica("adulto dopo il «sì»: voce sì", C.decidi(adulto, "voce", "voce").ok)
    verifica("contrario: voce con una frase breve (non certa): no",
             C.decidi(adulto, "voce", "breve").motivo == "voce_incerta")
    verifica("contrario: in compagnia: voce no, testo sì",
             not C.decidi(adulto, "voce", "voce", {"compagnia"})
             and C.decidi(adulto, "testo", "voce", {"compagnia"}).ok)
    verifica("contrario: conserva_voce false: voce no",
             C.decidi(adulto, "voce", "voce", cfg=SimpleNamespace(conserva_voce=False)).motivo
             == "spenta")
    amm.voce_conservata = False
    verifica("contrario: chi amministra che ha detto no: voce no",
             not C.decidi(amm, "voce", "voce"))
    amm.voce_conservata = None
    cresciuto = UserProfile(name="Ugo", id="p-ugo", voce_conservata=True,
                            voce_conservata_da="p-amm")
    verifica("contrario: un adulto col «sì» dato da un tutore quando era minore: voce no",
             C.decidi(cresciuto, "voce", "voce").motivo == "senza_consenso")
    cresciuto.voce_conservata_da = "p-ugo"
    verifica("…e col «sì» suo, sì", C.decidi(cresciuto, "voce", "voce").ok)
    verifica("minore per la sola fascia scritta a mano: minore",
             C.categoria(UserProfile(name="X", fascia="ragazzi")) == "minore")
    try:
        C.decidi(adulto, "foto")
        verifica("cosa sconosciuta: errore", False)
    except ValueError:
        verifica("cosa sconosciuta: errore", True)

    # ───────── registro dei turni ─────────
    cfg = Config()
    cfg.turn_log_dir = str(tmp / "registro")
    cfg.memory_db = str(tmp / "memoria.db")     # mai quella vera (svuota tutto, 12/10 sera)
    cfg.turn_log_days = 60
    cfg.conserva_voce, cfg.conserva_voce_mb = True, 2000
    cons = C.Conservazione(cfg, reg, log=lambda m: None)
    # La rotazione del giorno parte in secondo piano al primo salvataggio: qui la si chiama a
    # mano, quando serve (niente thread che corrono con la prova)
    cons._ruotata_il = datetime.date.today()
    log = TurnLog(cfg.turn_log_dir, 60, conserva=cons)
    cons.turnlog = log
    oggi = datetime.date.today().isoformat()

    def turno(nome, modo="voce", livello="familiare", testo="accendi la luce della cucina",
              **extra):
        voce = {"nome": nome, "modo": modo, **({"id": reg.get(nome).id} if reg.get(nome)
                                                else {}), **extra.pop("voce", {})}
        return {"inizio": f"{oggi}T10:00:0{len(extra) % 10}.000", "livello": livello,
                "voce": voce if nome else None, "testo": testo, "esito": "risposta",
                "risposta": "Fatto, luce accesa.",
                "tool": [{"nome": "casa_comando", "argomenti": {"comando": "accendi"},
                          "ok": True}], **extra}

    casi = {"adulto": turno("Ginevra"),
            "minore": turno("Leo"),
            "minore_fascia": turno("Ginevra", ascolto={"fascia": "ragazzi"}),
            "ospite": turno(None, livello="ospite"),
            # Come lo scrive il ciclo (minori.piu_protetto): il nome del minore, «conversazione»
            "incerta": turno("Leo", modo="conversazione",
                             voce={"incerta": ["Primo", "Leo"], "punteggio": 0.489}),
            "grigia": turno("Ginevra", modo="conversazione")}
    for k, r in casi.items():
        r["caso"] = k
        cons.al_turno(r)
        log.write(r)
    righe = {r["caso"]: r for r in (json.loads(x) for x in (
        Path(cfg.turn_log_dir) / f"turni-{oggi}.jsonl").read_text(encoding="utf-8").splitlines())}
    for k in ("adulto", "minore", "minore_fascia", "incerta"):
        # Dal 16/10 (decisione 0031) il minore (dal profilo o dalla sola fascia nel turno) e il
        # dubbio tra un adulto e un minore tengono le parole come l'adulto
        r = righe[k]
        verifica(f"registro «{k}»: le parole, la risposta e gli argomenti restano",
                 r["testo"] == "accendi la luce della cucina"
                 and r["risposta"] == "Fatto, luce accesa." and r["tool"][0].get("argomenti")
                 and "conserva" not in r, str(r)[:300])
    for k in ("ospite", "grigia"):
        r = righe[k]
        verifica(f"registro, contrario «{k}»: niente parole, restano i numeri",
                 r["testo"] is None and r["risposta"] is None and r.get("testo_parole") == 5
                 and "argomenti" not in r["tool"][0] and r["tool"][0]["nome"] == "casa_comando",
                 str(r)[:300])
    verifica("il ciclo segna il motivo nel turno (letto dall'ombra degli eventi)",
             righe["grigia"]["conserva"] == {"testo": False, "motivo": "voce_incerta"}
             and righe["ospite"]["conserva"] == {"testo": False, "motivo": "ospite"}
             and "conserva" not in righe["adulto"] and "conserva" not in righe["minore"])
    # Righe scritte da altri (cassetto, schermi) senza il segno: decide la conservazione
    log.write({"inizio": f"{oggi}T11:00:00", "livello": "familiare", "testo": "foto.jpg",
               "voce": {"nome": "Leo", "modo": "schermo"}, "caso": "altri"})
    log.write({"inizio": f"{oggi}T11:00:01", "livello": "familiare", "testo": "foto.jpg",
               "voce": {"nome": None, "modo": "schermo"}, "caso": "altri_ospite"})
    ultime = [json.loads(x) for x in (Path(cfg.turn_log_dir) / f"turni-{oggi}.jsonl").read_text(
        encoding="utf-8").splitlines()][-2:]
    verifica("una riga di altri senza segno, di un minore → con le parole",
             ultime[0]["testo"] == "foto.jpg", str(ultime[0]))
    verifica("contrario: una riga di altri senza segno e senza nessuno → senza parole",
             ultime[1]["testo"] is None, str(ultime[1]))

    # ───────── i turni come li scrive il ciclo (16/10, revisione della PR #106) ─────────
    # Il ciclo vero (`Ciclo._riconosci_voce` con le impronte sintetiche di prova_voci_famiglia:
    # Carlo amministra ed è tutore di Luca, 14 anni) scrive il campo `voce`; da lì decide la
    # conservazione, nel registro dei turni e per la voce
    import prova_voci_famiglia as VF
    from calliope.speaker_id import SpeakerContext  # noqa: F401  (il ciclo lo usa)

    def dal_ciclo(sc_carlo, sc_luca, voce_s=2.0, in_session=False, prev=None, prima=None):
        rg, scx, cx, _r = VF.ciclo_finto()
        cx.speaker = VF.VoceFinta()
        if prima is not None:
            VF.riconosci(cx, scx, VF.frase_con(*prima), 2.0)
        n, how, lv, v, _t = VF.riconosci(cx, scx, VF.frase_con(sc_carlo, sc_luca), voce_s,
                                         in_session=in_session, prev=prev)
        return rg, {"inizio": f"{oggi}T12:00:00.000", "livello": lv, "voce": v,
                    "testo": "domani c'è la gita al lago", "esito": "risposta",
                    "risposta": "Che bello, buona gita."}

    cfg_c = Config()
    cfg_c.turn_log_dir = str(tmp / "registro-ciclo")
    cfg_c.memory_db = str(tmp / "memoria-ciclo.db")
    cfg_c.conserva_voce = True
    casi_ciclo = {
        "incerta (caso 1 del 06/10: Carlo 0,489, Luca 0,46 → Luca)": ((0.489, 0.46, 3.19), True),
        "minore_vicino (Carlo 0,62, Luca 0,52 → Carlo familiare)": ((0.62, 0.52, 2.0), True),
        "Luca netto": ((0.20, 0.70, 2.0), True),
        "Carlo netto": ((0.72, 0.20, 2.0), True),
    }
    for nome, ((a, b, vs), atteso) in casi_ciclo.items():
        rg, rec = dal_ciclo(a, b, vs, in_session=True, prev="Carlo")
        cc = C.Conservazione(cfg_c, rg, log=lambda m: None)
        cc._ruotata_il = datetime.date.today()
        tl = TurnLog(cfg_c.turn_log_dir, 60, conserva=cc)
        cc.al_turno(rec, audio_ciclo := (0.2 * np.sin(np.arange(16000) / 7)).astype(np.float32),
                    16000)
        tl.write(dict(rec))
        scritto = json.loads((Path(cfg_c.turn_log_dir) / f"turni-{oggi}.jsonl").read_text(
            encoding="utf-8").splitlines()[-1])
        verifica(f"ciclo vero, {nome}: il testo nel registro dei turni",
                 scritto["testo"] == "domani c'è la gita al lago" and "conserva" not in rec,
                 json.dumps(rec["voce"])[:300])
        dubbio = rec["voce"].get("modo") == "conversazione"
        verifica(f"ciclo vero, {nome}: la voce " + ("no (dubbio)" if dubbio else "sì"),
                 bool(rec.get("voce_file")) is not dubbio, json.dumps(rec)[:300])
    # Contrari dal ciclo: zona grigia (Carlo 0,45 nella sua conversazione, nessun minore in
    # mezzo), voce di nessuno, voce di nessuno vicina al profilo del minore (piu_protetto)
    for nome, (args, kw) in {
            "zona grigia (Carlo 0,45 nella sua conversazione)":
                ((0.45, 0.05, 2.0), {"in_session": True, "prev": "Carlo",
                                     "prima": (0.72, 0.20)}),
            # Issue #108 punto 3: chi amministra nella zona grigia della sua conversazione con il
            # minore vicino. Il ciclo scrive il dubbio (incerta, vale Luca), ma la voce migliore
            # è sotto `speaker_id_threshold`: resta fuori come la zona grigia (0031 punto 3)
            "zona grigia con il minore vicino (Carlo 0,45, Luca 0,44 → Luca, incerta)":
                ((0.45, 0.44, 2.0), {"in_session": True, "prev": "Carlo",
                                     "prima": (0.72, 0.20)}),
            "voce sconosciuta": ((0.10, 0.05, 2.0), {}),
            "voce di nessuno vicina al minore (Luca 0,44 sotto soglia → Luca per prudenza)":
                ((0.10, 0.44, 2.0), {})}.items():
        rg, rec = dal_ciclo(*args, **kw)
        cc = C.Conservazione(cfg_c, rg, log=lambda m: None)
        cc._ruotata_il = datetime.date.today()
        tl = TurnLog(cfg_c.turn_log_dir, 60, conserva=cc)
        cc.al_turno(rec, audio_ciclo, 16000)
        tl.write(dict(rec))
        scritto = json.loads((Path(cfg_c.turn_log_dir) / f"turni-{oggi}.jsonl").read_text(
            encoding="utf-8").splitlines()[-1])
        verifica(f"ciclo vero, contrario: {nome} → niente parole, niente voce",
                 scritto["testo"] is None and not rec.get("voce_file"),
                 json.dumps(rec["voce"])[:300])
        if "zona grigia con il minore" in nome:
            verifica("…il ciclo l'ha scritta col segno del dubbio, sotto il nome del minore, "
                     "e il motivo è la voce incerta",
                     rec["voce"].get("incerta") == ["Carlo", "Luca"]
                     and rec["voce"].get("nome") == "Luca"
                     and rec["voce"].get("modo") == "conversazione"
                     and rec.get("conserva") == {"testo": False, "motivo": "voce_incerta"},
                     json.dumps(rec)[:400])

    # ───────── voce ─────────
    sr = 16000
    tt = np.arange(sr * 2) / sr
    audio = (0.3 * np.sin(2 * np.pi * 220 * tt) + 0.05 * np.sin(2 * np.pi * 1300 * tt)).astype(
        np.float32)
    rec = turno("Ginevra")
    cons.al_turno(rec, audio, sr)
    f = rec.get("voce_file")
    verifica("voce dell'adulto con il sì: salvata nella sua cartella",
             bool(f) and f.startswith("p-adu/") and (cons.voce_dir / f).exists(), str(rec))
    if f:
        letto, sr2 = C.leggi_wav(cons.voce_dir / f)
        err = float(np.sqrt(np.mean((letto[:len(audio)] - audio) ** 2)))
        verifica("μ-law: si rilegge, 8 bit al campione, errore piccolo",
                 sr2 == sr and len(letto) == len(audio) and err < 0.01
                 and (cons.voce_dir / f).stat().st_size < len(audio) + 100, f"{err} {sr2}")
        if os.name == "posix":
            m = (cons.voce_dir / f).stat().st_mode & 0o777
            verifica("permessi del file 600", m == 0o600, oct(m))
        else:
            print("OK  permessi 600/700: solo su Linux (qui le ACL della cartella dell'utente)")
    rec = turno("Primo", livello="amministra")
    cons.al_turno(rec, audio, sr)
    verifica("chi amministra: voce salvata senza averlo detto", bool(rec.get("voce_file")))
    minore.voce_conservata, minore.voce_conservata_da = False, "p-amm"   # revocato
    for nome, r in (("minore con il consenso revocato dal tutore", turno("Leo")),
                    ("ospite", turno(None, livello="ospite")),
                    ("adulto senza consenso", turno("Ginevra")),
                    ("frase breve", turno("Primo", modo="breve")),
                    ("compagnia", turno("Primo", voce={"compagnia": {"voci": 2}})),
                    ("scritta", turno("Primo", modo="schermo", canale="scritto")),
                    ("ignorata", {**turno("Primo"), "esito": "ignorato"}),
                    ("incerta con un minore", turno("Primo", modo="conversazione",
                                                    voce={"minore_vicino": "Leo"})),
                    ("frase di sfida", {**turno("Primo"), "regole": ["sfida_risposta"]}),
                    ("codice detto", {**turno("Primo"), "tool": [
                        {"nome": "schermo_gestisci", "argomenti": {"codice": "******"}}]})):
        if nome == "adulto senza consenso":
            adulto.voce_conservata = None
        cons.al_turno(r, audio, sr)
        verifica(f"voce, contrario «{nome}»: non salvata", not r.get("voce_file"), str(r)[:200])
        adulto.voce_conservata = True
    verifica("nessun file per il minore col consenso revocato",
             not (cons.voce_dir / "p-min").exists())
    # Il consenso implicito dei tutori (16/10, decisione 0031): la voce del minore si tiene
    minore.voce_conservata = minore.voce_conservata_da = None
    rec = turno("Leo")
    cons.al_turno(rec, audio, sr)
    verifica("voce del minore col consenso implicito dei tutori: salvata nella sua cartella",
             bool(rec.get("voce_file")) and rec["voce_file"].startswith("p-min/"),
             str(rec)[:200])
    for nome, r in (("minore in un dubbio con un adulto",
                     turno("Leo", modo="conversazione",
                           voce={"incerta": ["Primo", "Leo"], "punteggio": 0.489})),
                    ("minore in compagnia", turno("Leo", voce={"compagnia": {"voci": 2}}))):
        cons.al_turno(r, audio, sr)
        verifica(f"voce, contrario «{nome}»: non salvata, il testo sì",
                 not r.get("voce_file") and "conserva" not in r, str(r)[:200])
    # Dal ciclo: _scrivi_turno prende l'audio del turno di questo rec, poi il registro dei turni
    from calliope.ciclo import Ciclo
    finto = SimpleNamespace(s=SimpleNamespace(conserva=cons, cfg=cfg, turns=log), ombra=None,
                            _turno=SimpleNamespace(audio=audio, scritto=None))
    rec = turno("Primo", livello="amministra")
    Ciclo._scrivi_turno(finto, rec)
    scritta = [json.loads(x) for x in (Path(cfg.turn_log_dir) / f"turni-{oggi}.jsonl").read_text(
        encoding="utf-8").splitlines()][-1]
    verifica("ciclo: la voce del turno salvata e citata nel registro dei turni",
             bool(scritta.get("voce_file")) and (cons.voce_dir / scritta["voce_file"]).exists())
    finto._turno = SimpleNamespace(audio=audio, scritto={"testo": "x"})
    rec = turno("Primo", livello="amministra")
    Ciclo._scrivi_turno(finto, rec)
    verifica("ciclo, contrario: un turno scritto non ha audio", not rec.get("voce_file"))

    # ───────── consenso e revoca ─────────
    n = cons.registrazioni("p-adu")
    tolte = cons.imposta_consenso(adulto, False)
    verifica("revoca: scelta nel profilo salvata, registrazioni cancellate",
             adulto.voce_conservata is False and tolte == n == 1 and reg.salvato >= 1
             and cons.registrazioni("p-adu") == 0 and adulto.voce_conservata_il == oggi)
    d = UserProfile.from_dict(adulto.to_dict(), "x")
    verifica("il consenso resta nel profilo (speakers.json)", d.voce_conservata is False)
    verifica("profilo di prima senza il campo: «mai detto»",
             UserProfile.from_dict({"name": "Z"}, "x").voce_conservata is None)

    # ───────── rotazione ─────────
    vecchio = (datetime.date.today() - datetime.timedelta(days=70)).isoformat()
    C._scrivi_privato(cons.voce_dir / "p-amm" / vecchio / "100000-000.wav",
                      C.wav_mulaw(audio, sr))
    C._scrivi_privato(cons.voce_dir / "p-adu" / oggi / "100000-000.wav", C.wav_mulaw(audio, sr))
    C._scrivi_privato(cons.voce_dir / "p-sconosciuto" / oggi / "1.wav", C.wav_mulaw(audio, sr))
    r = cons.ruota()
    verifica("rotazione: via il giorno oltre i 60, la persona senza consenso e l'id sconosciuto",
             not (cons.voce_dir / "p-amm" / vecchio).exists()
             and not (cons.voce_dir / "p-adu").exists()
             and not (cons.voce_dir / "p-sconosciuto").exists()
             and (cons.voce_dir / "p-amm" / oggi).exists() and r["persone"] == 2, str(r))
    verifica("rotazione: il minore col consenso dei tutori resta",
             cons.registrazioni("p-min") == 1)
    minore.tutori = ["p-via"]                     # il tutore tolto dalla casa
    r = cons.ruota()
    verifica("rotazione, contrario: il minore senza più un tutore valido via",
             not (cons.voce_dir / "p-min").exists() and r["persone"] == 1, str(r))
    minore.tutori = ["p-amm"]
    ieri = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    for g in (ieri, oggi):
        for i in range(3):
            C._scrivi_privato(cons.voce_dir / "p-amm" / g / f"x{i}.wav", C.wav_mulaw(audio, sr))
    giorno_mb = C._mb(cons.voce_dir / "p-amm" / oggi)
    cons.mb = giorno_mb * 1.2
    r = cons.ruota()
    verifica("tetto di spazio: via i giorni più vecchi, resta l'ultimo",
             r["tetto"] == 1 and not (cons.voce_dir / "p-amm" / ieri).exists()
             and (cons.voce_dir / "p-amm" / oggi).exists(), str(r))
    cons.mb = 2000

    # ───────── registro di prima ripulito una volta ─────────
    vecchia = Path(cfg.turn_log_dir) / f"turni-{ieri}.jsonl"
    vecchia.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in (
        {"inizio": f"{ieri}T09:00:00", "livello": "familiare", "testo": "quanto fa sette per otto",
         "voce": {"nome": "Leo", "modo": "voce"}, "risposta": "Cinquantasei."},
        {"inizio": f"{ieri}T09:01:00", "livello": "amministra", "testo": "che ore sono",
         "voce": {"nome": "Primo", "modo": "voce"}, "risposta": "Sono le nove."},
        {"inizio": f"{ieri}T09:02:00", "livello": "ospite", "testo": "il mio cane si chiama Fido",
         "voce": None, "risposta": "Bel nome."})) + "\nrotta{\n",
        encoding="utf-8")
    r = cons.ripulisci_registro()
    righe = vecchia.read_text(encoding="utf-8").splitlines()
    # Dal 16/10 (decisione 0031) la pulizia all'avvio non toglie più le parole dei minori
    verifica("registro di prima: le parole del minore e dell'adulto restano, la riga rotta pure",
             json.loads(righe[0])["testo"] == "quanto fa sette per otto"
             and json.loads(righe[1])["testo"] == "che ore sono" and righe[3] == "rotta{",
             str(righe)[:300])
    verifica("registro di prima, contrario: le parole dell'ospite tolte",
             r and r["turni"] == 1 and json.loads(righe[2])["testo"] is None, f"{r} {righe[2]}")
    verifica("una volta sola: il segno nella cartella", cons.ripulisci_registro() is None
             and (Path(cfg.turn_log_dir) / C.SEGNO_RIPULITO).exists())

    # ───────── eventi ─────────
    db = tmp / "conversazioni.db"
    disco = Disco.file(db, log=lambda m: None)
    cons.eventi = disco
    regs = Registri(disco, log=lambda m: None, conserva=cons.registro_su_disco)
    for chiave in ("persona:p-adu", "persona:p-min", "ospite:studio", "persona:ignoto"):
        rg = regs.della_corsia(chiave)
        rg.apri("persona")
        rg.aggiungi("detto_persona", 1, testo="la frase di prova", canale="voce")
    regs.scrivi()
    chiavi = set(disco.chiavi())
    # Dal 16/10 (decisione 0031) anche il registro del minore va su disco
    verifica("eventi: su disco l'adulto e il minore; ospite e profilo ignoto in memoria",
             chiavi == {"persona:p-adu", "persona:p-min"}
             and regs.della_corsia("ospite:studio").eventi(), str(chiavi))
    # Righe di un ospite scritte da una versione di prima: la rotazione le toglie
    vecchie = Registri(disco, log=lambda m: None)            # senza conservazione, come prima
    v = vecchie.della_corsia("ospite:cucina")
    v.apri("persona")
    v.aggiungi("detto_persona", 1, testo="frase di un ospite", canale="voce")
    vecchie.scrivi()
    verifica("(prima) l'ospite era su disco", "ospite:cucina" in disco.chiavi())
    regs2 = Registri(disco, log=lambda m: None, conserva=cons.registro_su_disco)
    rip = regs2.riprendi()
    verifica("riavvio: il registro del minore si riprende dal disco, quello dell'ospite no",
             rip["ripresi"] == 2
             and [e.dati.get("testo") for e in regs2.della_corsia("persona:p-min").eventi()
                  if e.tipo == "detto_persona"] == ["la frase di prova"]
             and not regs2.della_corsia("ospite:cucina").eventi(), str(rip))
    disco.ruota(60, effimero=lambda k: not cons.registro_su_disco(k))
    verifica("rotazione: via le righe dell'ospite, l'adulto e il minore restano",
             set(disco.chiavi()) == {"persona:p-adu", "persona:p-min"}, str(disco.chiavi()))
    # Il turno incerto nel registro di un adulto: le parole restano in memoria
    ev = Evento("persona:p-adu", 9, "c", None, time.time(), "detto_persona", 1, "modello",
                senza_parole("detto_persona", {"testo": "parole incerte", "canale": "voce"}))
    verifica("turno incerto: parole solo in memoria", "testo" not in per_disco(ev)
             and ev.dati["testo"] == "parole incerte")
    verifica("CAMPI_TESTO: tipi e campi dell'elenco chiuso",
             all(t in TIPI and set(c) <= set(TIPI[t].campi) for t, c in CAMPI_TESTO.items()))
    ev = Evento("persona:p-adu", 10, "c", None, time.time(), "dati_del_turno", 1, "turno",
                {"blocchi": [{"nome": "ricordi", "caratteri": 42},
                             {"nome": "turno", "testo": "ore 10"}]})
    verifica("dati_del_turno su disco: nomi e lunghezze",
             per_disco(ev)["blocchi"] == [{"nome": "ricordi", "caratteri": 42},
                                          {"nome": "turno", "caratteri": 6}])

    # ───────── svuotare ─────────
    adulto.voce_conservata = True
    rec = turno("Ginevra")
    cons.al_turno(rec, audio, sr)
    log.write(rec)
    r = cons.svuota("p-adu", "Ginevra")
    testi = [json.loads(x) for x in (Path(cfg.turn_log_dir) / f"turni-{oggi}.jsonl").read_text(
        encoding="utf-8").splitlines()]
    verifica("svuota una persona: voce, parole nei turni, eventi",
             r["voce"] == 1 and r["eventi"] >= 1 and r["turni"] >= 1
             and cons.registrazioni("p-adu") == 0 and "persona:p-adu" not in disco.chiavi()
             and not any(x.get("voce") and x["voce"].get("nome") == "Ginevra" and x.get("testo")
                         for x in testi), str(r))
    verifica("svuota una persona, contrario: chi amministra resta",
             cons.registrazioni("p-amm") > 0)
    r = cons.svuota()
    verifica("svuota tutto: niente voce, niente turni, niente eventi",
             not cons.voce_dir.exists() and not list(Path(cfg.turn_log_dir).glob("turni-*"))
             and disco.chiavi() == [], str(r))

    # ───────── il tool ─────────
    sc = SimpleNamespace(current_speaker="Ginevra", identified_by="voce", conferma_breve=False)
    ctx = SimpleNamespace(conserva=cons, speakers=reg, speaker_ctx=sc, turno=5, cfg=cfg,
                          regole=[])
    adulto.voce_conservata = None
    q = _dati_conservati(ctx, "consenso_voce")
    verifica("consenso: prima la domanda, con cosa e per quanto",
             q["ok"] is False and "60 giorni" in q["conferma"]
             and q["in_sospeso"]["argomenti"] == {"azione": "consenso_voce"}
             and adulto.voce_conservata is None, str(q))
    sc.identified_by, ctx.turno = "breve", 6
    r = _dati_conservati(ctx, "consenso_voce")
    verifica("il «sì» (anche breve) nella risposta dopo: consenso salvato",
             r["ok"] and adulto.voce_conservata is True, str(r))
    sc.identified_by = "schermo"
    adulto.voce_conservata = None
    r = _dati_conservati(ctx, "consenso_voce")
    verifica("contrario: scritto, mai il consenso", r["ok"] is False
             and adulto.voce_conservata is None and "in_sospeso" not in r)
    sc.identified_by = "conversazione"
    r = _dati_conservati(ctx, "consenso_voce")
    verifica("contrario: zona grigia, mai il consenso", r["ok"] is False
             and "in_sospeso" not in r)
    sc.current_speaker, sc.identified_by = "Leo", "voce"
    r = _dati_conservati(ctx, "consenso_voce")
    verifica("contrario: un minore non può dare il consenso", r["ok"] is False
             and minore.voce_conservata is None and "genitori" in r["conferma"]
             and "in_sospeso" not in r, str(r))
    r = _dati_conservati(ctx, "consenso_voce", "Leo")
    verifica("contrario: nemmeno nominandosi", r["ok"] is False
             and minore.voce_conservata is None)
    # Il consenso implicito dei tutori (16/10, decisione 0031 aggiornata)
    r = _dati_conservati(ctx, "revoca_voce")
    verifica("contrario: un minore non revoca da solo il consenso dei tutori", r["ok"] is False
             and minore.voce_conservata is None and C.consenso_voce(minore, reg))
    r = _dati_conservati(ctx, "stato")
    verifica("stato per un minore: i testi, i genitori, la voce decisa alla registrazione",
             r["ok"] and "60 giorni" in r["conferma"] and "genitori" in r["conferma"]
             and "voce sì" in r["conferma"] and "decisa alla registrazione" in r["conferma"],
             str(r))
    sc.current_speaker, ctx.turno = "Primo", 20
    r = _dati_conservati(ctx, "consenso_voce", "Leo")
    verifica("tutore: con il consenso implicito nessuna domanda («la tengo già»)",
             r["ok"] and "già" in r["conferma"] and "in_sospeso" not in r
             and minore.voce_conservata is None, str(r))
    # La revoca di un tutore: la stessa conferma di «svuota»
    sc.identified_by, sc.minore_vicino = "conversazione", "Leo"
    r = _dati_conservati(ctx, "revoca_voce", "Leo")
    verifica("contrario: il tutore nel dubbio col minore non revoca",
             r["ok"] is False and minore.voce_conservata is None, str(r))
    sc.minore_vicino = None
    sc.identified_by, sc.conferma_breve = "breve", False
    r = _dati_conservati(ctx, "revoca_voce", "Leo")
    verifica("contrario: un «sì» breve senza l'impronta compatibile non revoca",
             r["ok"] is False and minore.voce_conservata is None, str(r))
    sc.current_speaker, sc.identified_by = "Ginevra", "voce"
    r = _dati_conservati(ctx, "revoca_voce", "Leo")
    verifica("contrario: un adulto che non è tutore non revoca la voce del minore",
             r["ok"] is False and minore.voce_conservata is None)
    r = _dati_conservati(ctx, "consenso_voce", "Primo")
    verifica("contrario: per la voce di un altro adulto decide solo lui",
             r["ok"] is False and "in_sospeso" not in r and amm.voce_conservata is None)
    sc.current_speaker = "Primo"
    C._scrivi_privato(cons.voce_dir / "p-min" / oggi / "1.wav", C.wav_mulaw(audio, sr))
    r = _dati_conservati(ctx, "revoca_voce", "Leo")
    verifica("tutore con la voce: revoca subito, le registrazioni del minore cancellate",
             r["ok"] and minore.voce_conservata is False and minore.voce_conservata_da == "p-amm"
             and r["cancellate"] == 1 and cons.registrazioni("p-min") == 0
             and "voce di Leo" in r["conferma"] and not C.consenso_voce(minore, reg), str(r))
    sc.current_speaker = "Leo"
    r = _dati_conservati(ctx, "stato")
    verifica("stato per il minore dopo la revoca: la voce no, decisa dai genitori",
             "voce no" in r["conferma"] and "genitori" in r["conferma"], str(r))
    # Il consenso ridato a mano dopo la revoca: domanda, poi il «sì» con la conferma di «svuota»
    sc.current_speaker, ctx.turno = "Primo", 30
    q = _dati_conservati(ctx, "consenso_voce", "Leo")
    verifica("tutore: dopo la revoca, prima la domanda sulla voce del minore",
             q["ok"] is False and "voce di Leo" in q["conferma"]
             and q["in_sospeso"]["argomenti"] == {"azione": "consenso_voce", "persona": "Leo"}
             and minore.voce_conservata is False, str(q))
    sc.identified_by, sc.conferma_breve, ctx.turno = "breve", False, 31
    r = _dati_conservati(ctx, "consenso_voce", "Leo")
    verifica("contrario: il «sì» del minore accanto (breve, impronta non compatibile) non vale",
             r["ok"] is False and minore.voce_conservata is False, str(r))
    sc.conferma_breve, ctx.turno = True, 32
    r = _dati_conservati(ctx, "consenso_voce", "Leo")
    verifica("tutore: il «sì» breve con l'impronta compatibile, salvato con chi l'ha dato",
             r["ok"] and minore.voce_conservata is True and minore.voce_conservata_da == "p-amm"
             and minore.voce_conservata_il == oggi and C.consenso_voce(minore, reg), str(r))
    verifica("…e chi amministra non ha cambiato la sua scelta", amm.voce_conservata is None)
    sc.identified_by, sc.conferma_breve = "voce", False
    sc.current_speaker = None
    r = _dati_conservati(ctx, "stato")
    verifica("contrario: ospite, niente", r["ok"] is False)
    sc.current_speaker, sc.identified_by = "Ginevra", "breve"
    adulto.voce_conservata = True
    r = _dati_conservati(ctx, "revoca_voce")
    verifica("revoca a voce (anche breve): subito, senza domanda",
             r["ok"] and adulto.voce_conservata is False)
    sc.identified_by, ctx.turno = "voce", 10
    r = _dati_conservati(ctx, "svuota", "Leo")
    verifica("contrario: svuota da chi non amministra, rifiutato", r["ok"] is False
             and "in_sospeso" not in r)
    sc.current_speaker = "Primo"
    q = _dati_conservati(ctx, "svuota", "Ginevra")
    ctx.turno = 11
    r = _dati_conservati(ctx, "svuota", "Ginevra")
    verifica("svuota di chi amministra: domanda, poi il «sì»",
             q["ok"] is False and "di Ginevra" in q["conferma"] and r["ok"], f"{q} {r}")
    r = _dati_conservati(ctx, "svuota", "Nessuno")
    verifica("svuota, contrario: persona sconosciuta", r["ok"] is False)
    spec = conserva_specs()[0]
    verifica("tool: famiglia, azione, classe con «stato» in sola lettura e «svuota» distruttiva",
             spec.name == "dati_conservati" and spec.risk == "azione"
             and spec.classe.sola_lettura[1] == frozenset({"stato"})
             and "svuota" in spec.classe.distruttiva)

    # ───────── il «sì» breve di un tutore che non amministra (16/10, issue #108) ─────────
    # Decisione di chi amministra: un tutore conferma con il «sì» breve compatibile (stessa
    # soglia e stesse condizioni della conferma breve di chi amministra) la voce di un suo
    # figlio. Con il SpeakerContext vero: `aggiorna_conversazione` decide `breve_impronta_ok`
    # (fino al 16/10 `breve_compatibile`, nome già usato da un modo di si_breve: issue #114)
    from calliope.conferme import admin_confermato
    from calliope.speaker_id import SpeakerContext as _SCt
    tutrice = UserProfile(name="Marta", id="p-mar")
    figlia = UserProfile(name="Nina", id="p-nin", tutori=["p-amm", "p-mar"],
                         nascita=f"{datetime.date.today().year - 8}-05-02")
    reg_t = Registro(amm, adulto, tutrice, figlia)
    reg_t.cfg = cfg
    sct = _SCt(reg_t)
    ctx_t = SimpleNamespace(conserva=cons, speakers=reg_t, speaker_ctx=sct, turno=40, cfg=cfg,
                            regole=[])

    def _bc_di(s):
        # getattr: prima della #114 il campo si chiamava `breve_compatibile` e le verifiche
        # falliscono
        return getattr(s, "breve_impronta_ok", False)

    def _bc():
        return _bc_di(sct)

    verifica("issue #114: l'attributo del SpeakerContext si chiama `breve_impronta_ok`, non più "
             "come il modo `breve_compatibile` di si_breve",
             hasattr(sct, "breve_impronta_ok") and not hasattr(sct, "breve_compatibile"))

    def frase_t(nome, how, punteggio=None, altro=False, in_session=True):
        """Una frase come la decide il ciclo (_riconosci_voce): chi, come, il punteggio contro
        il profilo di chi vale e se un altro profilo è almeno altrettanto vicino."""
        sct.aggiorna_conversazione(nome, how, in_session, punteggio, altro)
        sct.current_speaker, sct.identified_by = nome, how
        ctx_t.turno += 1
        ctx_t.regole = []

    def domanda_tutrice():
        """Marta, riconosciuta dalla voce, chiede di tenere la voce di Nina (dopo una revoca)."""
        figlia.voce_conservata, figlia.voce_conservata_da = False, "p-amm"
        cons.proposte.pop("voce:p-nin:p-mar", None)     # la domanda di prima non è aperta
        frase_t("Marta", "voce", 0.62, in_session=False)
        return _dati_conservati(ctx_t, "consenso_voce", "Nina")

    q = domanda_tutrice()
    verifica("tutrice che non amministra: con la voce prima la domanda sulla voce della figlia",
             q["ok"] is False and q["in_sospeso"]["argomenti"] == {"azione": "consenso_voce",
                                                                     "persona": "Nina"}, str(q))
    frase_t("Marta", "breve", 0.45)
    verifica("il «sì» breve compatibile della tutrice: compatibile ma non conferma di chi "
             "amministra", _bc() and not sct.conferma_breve
             and not admin_confermato(ctx_t), f"{_bc()} {sct.conferma_breve}")
    r = _dati_conservati(ctx_t, "consenso_voce", "Nina")
    verifica("tutrice: il «sì» breve compatibile dà il consenso, salvato con chi l'ha dato e con "
             "la regola nel registro", r["ok"] and figlia.voce_conservata is True
             and figlia.voce_conservata_da == "p-mar"
             and "conferma_breve_tutore" in ctx_t.regole, f"{r} {ctx_t.regole}")
    # I contrari: punteggio sotto `speaker_conferma_breve_soglia`, un altro profilo più vicino
    # (il minore accanto che dice «sì»), una conversazione nuova senza la sua voce sicura
    for nome_c, kw in {"punteggio sotto la soglia della conferma breve (0,30)":
                           {"punteggio": 0.30},
                       "un altro profilo vicino almeno quanto lei (la figlia accanto)":
                           {"punteggio": 0.45, "altro": True},
                       "senza la sua voce sicura nella conversazione":
                           {"punteggio": 0.45, "in_session": False}}.items():
        domanda_tutrice()
        frase_t("Marta", "breve", **kw)
        r = _dati_conservati(ctx_t, "consenso_voce", "Nina")
        verifica(f"contrario, tutrice: {nome_c} → niente consenso",
                 r["ok"] is False and figlia.voce_conservata is False
                 and not _bc() and "conferma_breve_tutore" not in ctx_t.regole,
                 str(r))
    # La revoca con il «sì» breve compatibile della tutrice; con quello di chi non è tutore no
    figlia.voce_conservata, figlia.voce_conservata_da = True, "p-mar"
    frase_t("Marta", "voce", 0.62, in_session=False)
    frase_t("Marta", "breve", 0.44)
    C._scrivi_privato(cons.voce_dir / "p-nin" / oggi / "1.wav", C.wav_mulaw(audio, sr))
    r = _dati_conservati(ctx_t, "revoca_voce", "Nina")
    verifica("tutrice: la revoca con il «sì» breve compatibile, registrazioni cancellate",
             r["ok"] and figlia.voce_conservata is False and r["cancellate"] == 1
             and "conferma_breve_tutore" in ctx_t.regole, str(r))
    figlia.voce_conservata = True
    frase_t("Marta", "breve", 0.30)
    r = _dati_conservati(ctx_t, "revoca_voce", "Nina")
    verifica("contrario, tutrice: revoca con un «sì» breve non compatibile rifiutata",
             r["ok"] is False and figlia.voce_conservata is True, str(r))
    frase_t("Ginevra", "voce", 0.62, in_session=False)
    frase_t("Ginevra", "breve", 0.45)
    r = _dati_conservati(ctx_t, "revoca_voce", "Nina")
    verifica("contrario: il «sì» breve compatibile di chi non è tutore non vale per la voce "
             "di un minore", r["ok"] is False and figlia.voce_conservata is True
             and _bc(), str(r))
    frase_t("Nina", "voce", 0.62, in_session=False)
    frase_t("Nina", "breve", 0.45)
    r = _dati_conservati(ctx_t, "revoca_voce", "Nina")
    verifica("contrario: il minore con il «sì» breve compatibile non revoca da solo",
             r["ok"] is False and figlia.voce_conservata is True, str(r))
    # «Svuota» resta di chi amministra: il «sì» breve compatibile di una tutrice non basta
    frase_t("Marta", "voce", 0.62, in_session=False)
    frase_t("Marta", "breve", 0.45)
    r = _dati_conservati(ctx_t, "svuota", "Nina")
    verifica("contrario: «svuota» col «sì» breve di una tutrice che non amministra, rifiutato",
             r["ok"] is False and "in_sospeso" not in r, str(r))
    # Issue #114 punto 4: un tutore che amministra (Primo) conferma con `conferma_breve`, come
    # sempre; la regola `conferma_breve_tutore` si scrive solo per chi non amministra
    figlia.voce_conservata, figlia.voce_conservata_da = False, "p-mar"
    cons.proposte.pop("voce:p-nin:p-amm", None)
    frase_t("Primo", "voce", 0.62, in_session=False)
    q = _dati_conservati(ctx_t, "consenso_voce", "Nina")
    frase_t("Primo", "breve", 0.45)
    r = _dati_conservati(ctx_t, "consenso_voce", "Nina")
    verifica("tutore che amministra: il «sì» breve passa da conferma_breve, senza la regola "
             "conferma_breve_tutore", q["ok"] is False and r["ok"] and sct.conferma_breve
             and figlia.voce_conservata is True and figlia.voce_conservata_da == "p-amm"
             and "voce_consenso" in ctx_t.regole
             and "conferma_breve_tutore" not in ctx_t.regole, f"{q} {r} {ctx_t.regole}")

    # ───────── il «sì» breve del tutore dal ciclo vero e da ToolRegistry.call (#114) ─────────
    # Issue #114 punto 1: sopra `altro` è passato a mano. Qui lo decide il `Ciclo` vero
    # (`_riconosci_voce`: `altro`, `minori.piu_protetto`, la compagnia) con le impronte sintetiche
    # di prova_voci_famiglia, e il tool passa da `ToolRegistry.call` con il livello del ciclo.
    # Carlo qui è un tutore che **non** amministra (solo nel registro finto di questa prova);
    # Luca, 14 anni, ha la voce revocata e Carlo chiede di tenerla di nuovo
    from calliope.tools.registry import ToolRegistry
    from calliope.tools.spec import ToolContext

    def ciclo_tutore():
        rg, scx, cx, regole_c = VF.ciclo_finto()
        cx.speaker = VF.VoceFinta()
        rg.cfg.turn_log_dir = str(tmp / "registro-tutore")
        rg.cfg.conserva_voce = True
        rg.users["Carlo"].admin = False
        luca = rg.users["Luca"]
        luca.voce_conservata, luca.voce_conservata_da = False, "carlo-id"
        cx_cons = C.Conservazione(rg.cfg, rg, log=lambda m: None)
        cx_cons._ruotata_il = datetime.date.today()
        tr = ToolRegistry()
        for s_ in conserva_specs():
            tr.register(s_)
        tc = ToolContext(cfg=rg.cfg, speakers=rg, speaker_ctx=scx, speaker=None,
                         conserva=cx_cons)
        return rg, scx, cx, tr, tc, luca

    def chiama(tr, tc, scx, persona="Luca", azione="consenso_voce"):
        tc.turno += 1
        tc.regole = []
        return json.loads(tr.call("dati_conservati", {"azione": azione, "persona": persona},
                                  tc, scx.current_level))

    def domanda_carlo(cx, scx, tr, tc):
        """Carlo, riconosciuto dalla voce in una frase intera, chiede di tenere la voce di Luca."""
        VF.riconosci(cx, scx, VF.frase_con(0.72, 0.20), 2.5)
        return chiama(tr, tc, scx)

    rg, scx, cx, tr, tc, luca = ciclo_tutore()
    q = domanda_carlo(cx, scx, tr, tc)
    verifica("ciclo vero: Carlo (tutore, non amministra) dalla voce → la domanda sulla voce di "
             "Luca", scx.current_speaker == "Carlo" and scx.identified_by == "voce"
             and scx.current_level == "familiare" and q["ok"] is False
             and q.get("in_sospeso", {}).get("argomenti") == {"azione": "consenso_voce",
                                                              "persona": "Luca"}, str(q))
    n_, how_, lv_, v_, _t = VF.riconosci(cx, scx, VF.frase_con(0.45, 0.20), 0.6,
                                         in_session=True, prev="Carlo")
    r = chiama(tr, tc, scx)
    verifica("ciclo vero: il «sì» breve di Carlo (0,45, Luca lontano) → breve_impronta_ok, "
             "consenso dato da ToolRegistry.call con la regola conferma_breve_tutore",
             (n_, how_) == ("Carlo", "breve") and _bc_di(scx) and not scx.conferma_breve
             and r.get("ok") is True and luca.voce_conservata is True
             and luca.voce_conservata_da == "carlo-id" and "conferma_breve_tutore" in tc.regole,
             f"{n_} {how_} {r} {tc.regole}")
    # La revoca, allo stesso modo
    VF.riconosci(cx, scx, VF.frase_con(0.72, 0.20), 2.5)
    VF.riconosci(cx, scx, VF.frase_con(0.46, 0.15), 0.7, in_session=True, prev="Carlo")
    r = chiama(tr, tc, scx, azione="revoca_voce")
    verifica("ciclo vero: la revoca col «sì» breve di Carlo da ToolRegistry.call",
             r.get("ok") is True and luca.voce_conservata is False
             and "conferma_breve_tutore" in tc.regole, f"{r} {tc.regole}")

    # I contrari, ognuno col suo ciclo: la domanda di Carlo è aperta, poi la frase breve
    contrari_ciclo = {
        # Il caso della revisione: Luca accanto dice «sì», più vicino a sé (0,47) che a Carlo
        # (0,44). La frase breve vale Carlo (chi parlava; 0,47 è sotto la soglia piena, quindi
        # `piu_protetto` non la sposta), ma il ciclo vede che un altro profilo è più vicino
        "il «sì» di Luca accanto (Luca 0,47, Carlo 0,44: vale Carlo, `altro` dal ciclo)":
            ((0.44, 0.47), 0.6, False, ("Carlo", "breve")),
        # Luca sopra la soglia piena: `piu_protetto` sposta la frase breve su di lui
        "Luca sopra soglia (0,50, Carlo 0,44: vale Luca, il minore da solo)":
            ((0.44, 0.50), 0.6, False, ("Luca", "conversazione")),
        # In compagnia una frase breve non vale nessuno: ospite
        "in compagnia, il «sì» breve di Carlo (0,45) non vale nessuno":
            ((0.45, 0.20), 0.6, True, (None, None)),
        # In compagnia, la zona grigia: ToolRegistry.call vuole la voce nella frase
        "in compagnia, Carlo nella zona grigia (0,45 in una frase intera)":
            ((0.45, 0.20), 2.0, True, ("Carlo", "conversazione")),
    }
    for nome_c, ((s_c, s_l), durata, in_comp, atteso) in contrari_ciclo.items():
        rg, scx, cx, tr, tc, luca = ciclo_tutore()
        domanda_carlo(cx, scx, tr, tc)
        if in_comp:
            cx._compagnia_attiva = lambda: True
        n_, how_, lv_, v_, _t = VF.riconosci(cx, scx, VF.frase_con(s_c, s_l), durata,
                                             in_session=True, prev="Carlo")
        r = chiama(tr, tc, scx)
        verifica(f"ciclo vero, contrario: {nome_c} → niente consenso",
                 (n_, how_) == atteso and r.get("ok") is False and luca.voce_conservata is False
                 and not _bc_di(scx) and "conferma_breve_tutore" not in tc.regole
                 and "voce_consenso" not in tc.regole, f"{n_} {how_} {lv_} {r}")
        if "zona grigia" in nome_c:
            verifica("…fermata da ToolRegistry.call prima del tool (compagnia_voce_nella_frase)",
                     "compagnia_voce_nella_frase" in tc.regole, f"{tc.regole} {r}")
        if "il «sì» di Luca accanto" in nome_c:
            verifica("…il ciclo ha visto Luca più vicino (punteggio di Carlo ~0,44 sopra la "
                     "soglia della conferma breve: decide solo `altro`)",
                     scx.punteggio is not None and abs(scx.punteggio - 0.44) < 0.01
                     and scx.punteggio >= rg.cfg.speaker_conferma_breve_soglia,
                     str(scx.punteggio))

    # ───────── la maggiore età: il sì dei tutori non vale più (16/10, issue #108) ─────────
    # Nina compie 18 anni: il sì dei tutori valeva finché era minore. La prima rotazione cancella
    # le sue registrazioni (una riga nel journal con l'id), e «stato» le dice perché
    # (getattr: su main, prima della #108, la funzione non c'è e le verifiche falliscono)
    _scaduta = getattr(C, "voce_dei_tutori_scaduta", lambda p: False)
    righe_log = []
    cfg_m = Config()
    cfg_m.turn_log_dir = str(tmp / "registro-maggiore")
    cfg_m.memory_db = str(tmp / "memoria-maggiore.db")
    cfg_m.conserva_voce = True
    grande = UserProfile(name="Nina", id="p-nin", tutori=["p-amm", "p-mar"],
                         nascita=f"{datetime.date.today().year - 19}-01-02",
                         voce_conservata=True, voce_conservata_da="p-mar")
    sua = UserProfile(name="Ginevra", id="p-adu", voce_conservata=True)
    reg_m = Registro(amm, sua, tutrice, grande)
    reg_m.cfg = cfg_m
    cm = C.Conservazione(cfg_m, reg_m, log=righe_log.append)
    cm._ruotata_il = datetime.date.today()
    for pid in ("p-nin", "p-adu", "p-amm"):
        C._scrivi_privato(cm.voce_dir / pid / oggi / "1.wav", C.wav_mulaw(audio, sr))
    verifica("maggiorenne: adulta, e il sì dei tutori non vale più",
             C.categoria(grande) == "adulto" and not C.consenso_voce(grande, reg_m)
             and _scaduta(grande))
    verifica("contrari: un adulto col suo sì e chi amministra senza scelta non sono «scaduti»",
             not _scaduta(sua) and not _scaduta(amm)
             and not _scaduta(adulto) and not _scaduta(figlia))
    sc_m = SimpleNamespace(current_speaker="Nina", identified_by="voce", conferma_breve=False)
    ctx_m = SimpleNamespace(conserva=cm, speakers=reg_m, speaker_ctx=sc_m, turno=1, cfg=cfg_m,
                            regole=[])
    r = _dati_conservati(ctx_m, "stato")
    verifica("maggiorenne: «stato» dice che il sì dei genitori valeva finché era minorenne",
             r["ok"] and "voce no" in r["conferma"] and "minorenne" in r["conferma"], str(r))
    sc_m.current_speaker = "Ginevra"
    r = _dati_conservati(ctx_m, "stato")
    verifica("contrario: l'adulta col suo sì, «stato» senza la frase dei genitori",
             "voce sì" in r["conferma"] and "minorenne" not in r["conferma"], str(r))
    rm = cm.ruota()
    verifica("maggiorenne: la rotazione cancella le sue registrazioni e lo scrive con l'id",
             cm.registrazioni("p-nin") == 0 and rm.get("maggiorenni") == 1
             and any("p-nin" in x and "maggiorenne" in x for x in righe_log)
             and not any("Nina" in x for x in righe_log), f"{rm} {righe_log}")
    verifica("contrario: le registrazioni degli adulti col consenso restano",
             cm.registrazioni("p-adu") == 1 and cm.registrazioni("p-amm") == 1, str(rm))
    # Il suo sì da adulta, come lo scrive il tool (issue #114 punto 2): la domanda, poi il «sì»
    # con la sua voce. Il tool salva `voce_conservata_da` vuoto (None = l'ha deciso lei)
    grande.voce_conservata, grande.voce_conservata_da = True, "p-mar"     # il sì dei tutori
    sc_m.current_speaker, sc_m.identified_by = "Nina", "voce"
    ctx_m.turno = 5
    q = _dati_conservati(ctx_m, "consenso_voce")
    ctx_m.turno, ctx_m.regole = 6, []
    r = _dati_conservati(ctx_m, "consenso_voce")
    verifica("maggiorenne: il suo sì col tool (domanda, poi «sì»), salvato senza "
             "`voce_conservata_da` (l'ha deciso lei)",
             q["ok"] is False and "in_sospeso" in q and r["ok"]
             and grande.voce_conservata is True and grande.voce_conservata_da is None
             and "voce_consenso" in ctx_m.regole, f"{q} {r}")
    r = _dati_conservati(ctx_m, "stato")
    verifica("…e il suo sì da adulta vale (la frase dei genitori non c'è più)",
             "voce sì" in r["conferma"] and C.consenso_voce(grande, reg_m)
             and not _scaduta(grande), str(r))
    # L'altra forma accettata: il suo id in `voce_conservata_da` (il tool non la scrive)
    grande.voce_conservata_da = "p-nin"
    verifica("…e vale anche col suo id in `voce_conservata_da`",
             C.consenso_voce(grande, reg_m) and not _scaduta(grande))

    # ───────── la registrazione di un minore: il consenso alla voce implicito (16/10) ─────────
    # Decisione di chi amministra (16/10, 0031 aggiornata): registrando un minore chi amministra
    # dà il consenso a tenere la sua voce. Il registro e i tool veri di prova_sicurezza
    import prova_sicurezza as PS
    from calliope.speaker_id import SpeakerContext as _SC, SpeakerRegistry as _SR
    from calliope.tools.spec import ToolContext
    path_prima = _SR.PATH
    try:
        regr = PS.registro_finto()
        scr = _SC(regr)
        ctxr = ToolContext(cfg=regr.cfg, speakers=regr, speaker_ctx=scr, speaker=None)
        strumenti = PS.Strumenti()
        nascita_g = f"{datetime.date.today().year - 9}-03-04"
        scr.current_speaker, scr.identified_by = "Bianca", "voce"
        out = strumenti.call("registra_utente", {"nome": "gino", "nascita": nascita_g}, ctxr,
                             "familiare")
        verifica("registrazione, contrario: un adulto che non amministra non registra un minore "
                 "(e quindi non dà nessun consenso)", out.get("ok") is False
                 and regr.get("Gino") is None, str(out))
        scr.current_speaker, scr.sfida_superata = "Dario", True
        out = strumenti.call("registra_utente", {"nome": "gino", "nascita": nascita_g}, ctxr,
                             "amministra")
        scr.sfida_superata = False
        for _ in range(5):
            esito_r = scr.enroll_sample("gino", voiced_s=3.0)
        g = regr.get("Gino")
        dario_id = regr.get("Dario").id
        verifica("registrazione di un minore da chi amministra: la voce col consenso implicito",
                 esito_r == "fatto" and g is not None and C.categoria(g) == "minore"
                 and g.voce_conservata is True and g.voce_conservata_da == dario_id
                 and g.tutori == [dario_id] and C.consenso_voce(g, regr)
                 and C.decidi(g, "voce", "voce", registry=regr).ok,
                 f"{out} {g and g.to_dict().get('voce_conservata_da')}")
        verifica("…e resta nel profilo (speakers.json)",
                 _SR.PATH.exists() and any(d.get("voce_conservata_da") == dario_id
                                           for d in json.loads(_SR.PATH.read_text("utf-8"))))
    finally:
        _SR.PATH = path_prima

    # ───────── l'archivio delle conversazioni (12/10 sera) ─────────
    from calliope.ciclo import Ciclo
    from calliope.conversazione import Conversazione, turni as turni_conv
    from calliope.conversazioni import (ArchivioConversazioni, load_conversazioni,
                                        senza_non_conservati)
    verifica("decidi, conversazioni: adulto, chi amministra e minore sì; ospite no",
             C.decidi(adulto, "conversazioni").ok and C.decidi(amm, "conversazioni").ok
             and C.decidi(minore, "conversazioni").ok and not C.decidi(None, "conversazioni"))
    verifica("conversazioni_su_disco: adulto e minore sì, profilo tolto no",
             cons.conversazioni_su_disco("p-adu") is True
             and cons.conversazioni_su_disco("p-min") is True
             and cons.conversazioni_su_disco("p-tolto") is False)
    verifica("conversazioni_su_disco: profili non letti → «non so» (None)",
             C.Conservazione(cfg, Registro(), log=lambda m: None)
             .conversazioni_su_disco("p-adu") is None)

    arch = ArchivioConversazioni(tmp / "conv.db", giorni=cons.giorni, log=lambda m: None,
                                 avvia=False, conserva=cons.conversazioni_su_disco)
    cons.conversazioni = arch
    nomi = {"p-adu": "Ginevra", "p-min": "Leo", "p-amm": "Primo"}

    def archivia(chi, testo, meta=None, conv=None):
        conv = conv or Conversazione(f"persona:{chi}" if chi else "ospite:studio")
        conv.owner, conv.last_turn_at = chi, time.monotonic()
        m = {"role": "user", "content": testo, **({"_turno": meta} if meta else {})}
        msgs = [m, {"role": "assistant", "content": "Va bene."}]
        conv.history += msgs
        arch.archivia(conv, turni_conv(msgs), chi, nomi.get(chi), ospite=chi is None)
        return conv

    def su_disco():
        return {(p, o) for p, o in arch.db.execute("SELECT persona, ospite FROM conversazioni")}

    def parole_su_disco():
        return " ".join(str(d) for (d,) in arch.db.execute("SELECT domanda FROM turni"))

    ca = archivia("p-adu", "il mio libro preferito è il barone rampante")
    cm = archivia("p-min", "domani ho la verifica di storia")
    co = archivia(None, "sono un ospite e il mio cane si chiama Fido")
    verifica("adulto: la conversazione su disco", ("p-adu", 0) in su_disco()
             and "barone" in parole_su_disco(), str(su_disco()))
    verifica("minore: la conversazione su disco (16/10, decisione 0031)",
             ("p-min", 0) in su_disco() and "verifica" in parole_su_disco())
    verifica("contrario: ospite, niente su disco", not any(o for _p, o in su_disco())
             and "Fido" not in parole_su_disco())
    verifica("minore: la conversazione nell'archivio su disco (ricerca e scheda)",
             arch.cerca("verifica di storia", "p-min")["risultati"]
             and arch.chat("p-min") and cm.archiviata_in == "disco"
             and ca.archiviata_in == "disco" and co.archiviata_in == "sessione")
    # Dopo un riavvio: un archivio nuovo sullo stesso file la ritrova
    rilegge = ArchivioConversazioni(tmp / "conv.db", giorni=cons.giorni, log=lambda m: None,
                                    avvia=False, conserva=cons.conversazioni_su_disco)
    verifica("minore: la conversazione si ritrova dopo un riavvio, l'ospite no",
             rilegge.cerca("verifica di storia", "p-min")["risultati"]
             and not rilegge.cerca("cane Fido", None, ospiti=True)["risultati"])
    rilegge.close()
    verifica("ospite: nella sessione, la trova solo chi cerca quelle degli ospiti",
             arch.cerca("cane Fido", None, ospiti=True)["risultati"]
             and not arch.cerca("cane Fido", "p-adu")["risultati"])
    # Il turno incerto: la decisione è quella del registro dei turni (testo_turno), il ciclo la
    # scrive nel `_turno` del messaggio
    finto = SimpleNamespace(s=SimpleNamespace(conserva=cons), _meta_turno={"luogo": "studio"})
    Ciclo._segna_conserva(finto, turno("Ginevra", modo="conversazione"))
    grigia = finto._meta_turno
    finto._meta_turno = None
    Ciclo._segna_conserva(finto, turno("Leo", modo="conversazione",
                                       voce={"incerta": ["Primo", "Leo"], "punteggio": 0.489}))
    dubbio = finto._meta_turno
    finto._meta_turno = {"luogo": "studio"}
    Ciclo._segna_conserva(finto, turno("Ginevra"))
    verifica("ciclo: la zona grigia segnata; il dubbio con un minore (dal 16/10) e l'adulto "
             "certo no", grigia == {"luogo": "studio", "conserva": False} and dubbio is None
             and finto._meta_turno == {"luogo": "studio"}, f"{grigia} {dubbio}")
    archivia("p-adu", "frase in zona grigia sul garage", meta=grigia, conv=ca)
    archivia("p-adu", "e poi il cavaliere inesistente", conv=ca)
    verifica("contrario: incerto, il turno non va su disco (l'adulto certo sì)",
             "garage" not in parole_su_disco() and "cavaliere" in parole_su_disco()
             and not arch.cerca("garage", "p-adu")["risultati"])
    # La conversazione in corso salvata: solo dell'adulto, senza il turno incerto
    ca.archiviati = len(ca.history)
    for c in (ca, cm, co):
        arch.salva_corrente(c)
    salvata = arch.leggi_corrente("persona:p-adu")
    verifica("conversazione in corso su disco: l'adulto senza il turno incerto",
             salvata and len(salvata["history"]) == 4 and "garage" not in json.dumps(salvata)
             and salvata["archiviati"] == 4, str(salvata)[:300])
    verifica("la conversazione in corso del minore su disco, quella dell'ospite no",
             sorted(arch.chiavi_correnti()) == ["persona:p-adu", "persona:p-min"],
             str(arch.chiavi_correnti()))
    verifica("senza_non_conservati: niente da togliere, lo stesso dizionario",
             senza_non_conservati({"history": [{"role": "user", "content": "x"}]})
             == {"history": [{"role": "user", "content": "x"}]})

    # Il riassunto di chiusura (12/10 sera): va su disco intero, quindi senza i turni incerti
    from calliope.compressione import Compressore, Lavoro
    from calliope.conversazioni import storia_conservata

    class Riassuntore:
        """Riassume ripetendo le domande che riceve (come il modello della voce e l'agente)."""
        nome, voce = "finto", True

        def __init__(self):
            self.visti = []

        def riassumi(self, lav, controlla=None):
            self.visti.append(lav)
            testi = [str(m.get("content") or "") for m in (lav.messaggi_voce or [])
                     + lav.da_riassumere if m.get("role") in ("user", "system")]
            return {"dati": {"argomenti": [t for t in testi if t and t != "S"][:12]},
                    "token": 1, "s": 0.0}

    def brain_di(conv):
        return SimpleNamespace(
            conv=conv, schemi=lambda: [],
            _system_messages=lambda: [{"role": "system", "content": "S"}],
            _riassunto_msgs=lambda c=None: (
                [{"role": "system", "content": conv.riassunto["testo"]}]
                if isinstance(conv.riassunto, dict) and conv.riassunto.get("testo") else []))

    def riassunto_su_disco(conv):
        for _ in range(250):
            r = archc.db.execute("SELECT riassunto, riassunto_dati FROM conversazioni "
                                "WHERE id = ?", (conv.id_archivio,)).fetchone()
            if r and r[0]:
                return " ".join(str(x) for x in r)
            time.sleep(0.02)
        return ""

    rf = Riassuntore()
    # Un archivio a parte: i conteggi dell'archivio di sopra restano quelli delle prove dopo
    archc = ArchivioConversazioni(tmp / "chiusura.db", giorni=cons.giorni, log=lambda m: None,
                                  avvia=False, conserva=cons.conversazioni_su_disco)

    def archivia_c(chi, testo, meta=None, conv=None):
        conv = conv or Conversazione(f"persona:{chi}")
        conv.owner, conv.last_turn_at = chi, time.monotonic()
        m = {"role": "user", "content": testo, **({"_turno": meta} if meta else {})}
        msgs = [m, {"role": "assistant", "content": "Va bene."}]
        conv.history += msgs
        archc.archivia(conv, turni_conv(msgs), chi, nomi.get(chi), ospite=False)
        return conv

    comp = Compressore(cfg, [rf], archc, log=lambda m: None)
    cc = archivia_c("p-adu", "parliamo della gita al lago di Braies")
    archivia_c("p-adu", "il codice del garage è quattro sette due", meta=grigia, conv=cc)
    archivia_c("p-adu", "e poi la cena da Ottavio", conv=cc)
    comp.chiudi(brain_di(cc), cc, "esci")
    disco = riassunto_su_disco(cc)
    verifica("chiusura: il riassunto su disco senza il turno incerto (zona grigia)",
             "Braies" in disco and "Ottavio" in disco and "garage" not in disco, disco[:300])
    verifica("…e il modello non l'ha nemmeno ricevuto (voce e trascrizione)",
             rf.visti and not any("garage" in str(m.get("content")) for m in
                                  rf.visti[-1].messaggi_voce + rf.visti[-1].da_riassumere))
    cn = archivia_c("p-adu", "parliamo della gita al lago di Braies")
    archivia_c("p-adu", "e poi la cena da Ottavio", conv=cn)
    comp.chiudi(brain_di(cn), cn, "esci")
    verifica("contrario: senza turni incerti il modello riceve la conversazione intera",
             "Ottavio" in riassunto_su_disco(cn) and len(rf.visti[-1].messaggi_voce) == 5,
             str(len(rf.visti[-1].messaggi_voce)))
    # Un riassunto di prima (compressione) fatto anche con il turno incerto: non entra in quello
    # di chiusura e non va su disco con la conversazione in corso
    cr = archivia_c("p-adu", "e poi la cena da Ottavio")
    cr.riassunto = {"tipo": "compressione", "testo": "Riassunto: il codice del garage, Braies",
                    "dati": {}, "non_conservati": True}
    comp.chiudi(brain_di(cr), cr, "esci")
    disco = riassunto_su_disco(cr)
    verifica("chiusura: un riassunto di prima fatto col turno incerto non entra",
             "Ottavio" in disco and "garage" not in disco, disco[:300])
    cr2 = archivia_c("p-adu", "e poi la cena da Ottavio")
    cr2.riassunto = {"tipo": "compressione", "testo": "Riassunto: la gita a Braies", "dati": {}}
    comp.chiudi(brain_di(cr2), cr2, "esci")
    verifica("contrario: un riassunto di prima pulito entra", "Braies" in riassunto_su_disco(cr2))
    verifica("conversazione in corso su disco: senza il riassunto fatto col turno incerto",
             senza_non_conservati({"history": [], "riassunto": cr.riassunto})["riassunto"]
             is None)
    verifica("contrario: il riassunto pulito resta nella conversazione in corso su disco",
             senza_non_conservati({"history": [], "riassunto": cr2.riassunto})["riassunto"]
             == cr2.riassunto)
    # La compressione segna il riassunto fatto con il turno incerto (in memoria vale)
    cs = Conversazione("persona:p-adu")
    finto_brain = SimpleNamespace(conv=cs, _archivia_turni=lambda: None,
                                  _stima_storia=lambda: 0, last_compressione=None,
                                  last_context=None)
    for incerto, atteso in ((True, True), (False, False)):
        cs.history = [{"role": "user", "content": "il codice del garage",
                       **({"_turno": grigia} if incerto else {})},
                      {"role": "assistant", "content": "Va bene."},
                      {"role": "user", "content": "la gita"}]
        cs.riassunto = None
        lav = Lavoro(cs, "compressione", cs.history[2], [dict(m) for m in cs.history[:2]],
                     None, [], "Ginevra", None, None)
        comp._applica_risultato(finto_brain, lav, {"argomenti": ["x"]}, "finto")
        verifica(f"compressione: riassunto segnato non conservato = {atteso}",
                 bool((cs.riassunto or {}).get("non_conservati")) is atteso, str(cs.riassunto))
    cs.history = [{"role": "user", "content": "il codice del garage", "_turno": grigia},
                  {"role": "assistant", "content": "Va bene."},
                  {"role": "user", "content": "la gita"}]
    verifica("storia_conservata: il turno incerto e le sue risposte via, il resto uguale",
             [m["content"] for m in storia_conservata(cs.history)] == ["la gita"])
    # La coda della conversazione chiusa per una pausa (in memoria nella nuova): segnata se tra
    # gli ultimi scambi c'è il turno incerto, così non va su disco con la conversazione in corso
    from calliope.brain import Brain
    for incerto, atteso in ((True, True), (False, False)):
        vecchia = Conversazione("persona:p-adu")
        vecchia.owner = "p-adu"
        vecchia.history = [{"role": "user", "content": "il codice del garage",
                            **({"_turno": grigia} if incerto else {})},
                           {"role": "assistant", "content": "Va bene."},
                           {"role": "user", "content": "la gita"},
                           {"role": "assistant", "content": "Bella."}]
        fb = SimpleNamespace(cfg=SimpleNamespace(conversazione_coda_scambi=3),
                             conv=Conversazione("persona:p-adu"))
        Brain._coda_della_chiusa(fb, vecchia)
        verifica(f"coda della chiusa: segnata non conservata = {atteso}",
                 bool((fb.conv.riassunto or {}).get("non_conservati")) is atteso
                 and "gita" in fb.conv.riassunto["testo"], str(fb.conv.riassunto)[:200])
    comp.close()
    archc.close()
    # Le conversazioni di prima del 12/10 (ospite, profilo tolto): via alla prima rotazione, con
    # le conversazioni in corso salvate; l'adulto, chi amministra e (dal 16/10) il minore restano
    vecchio = ArchivioConversazioni(tmp / "conv.db", log=lambda m: None, avvia=False,
                                    sessione=False)
    for chi in ("p-min", "p-tolto", "p-amm"):
        cv = Conversazione(f"persona:{chi}")
        cv.owner, cv.last_turn_at = chi, time.monotonic()
        cv.history = [{"role": "user", "content": f"frase di prima di {chi}"}]
        vecchio.archivia(cv, turni_conv(cv.history), chi, None, False)
        vecchio.salva_corrente(cv)
    vecchio.db.execute("INSERT INTO conversazioni (persona, nome, ospite, inizio) "
                       "VALUES (NULL, NULL, 1, ?)", (time.time(),))
    vecchio.db.execute("INSERT INTO correnti (chiave, stato, aggiornata) VALUES (?, ?, ?)",
                       ("ospite:studio", "{}", time.time()))
    vecchio.db.commit()
    vecchio.close()
    verifica("(prima) minore, ospite e profilo tolto erano su disco",
             {("p-min", 0), ("p-tolto", 0), (None, 1)} <= su_disco(), str(su_disco()))
    # Con i profili non letti la rotazione toglie solo gli ospiti
    arch.conserva = lambda p: None
    arch.togli_non_conservate()
    verifica("profili non letti: via gli ospiti, le persone restano",
             (None, 1) not in su_disco() and ("p-min", 0) in su_disco())
    arch.conserva = cons.conversazioni_su_disco
    n = arch.togli_non_conservate()
    # Dal 16/10 (decisione 0031) la pulizia non toglie più le conversazioni dei minori
    verifica("rotazione: via il profilo tolto, restano l'adulto, chi amministra e il minore",
             n == 1 and su_disco() == {("p-adu", 0), ("p-amm", 0), ("p-min", 0)}
             and "di prima di p-min" in parole_su_disco()
             and "di prima di p-tolto" not in parole_su_disco()
             and set(arch.chiavi_correnti()) == {"persona:p-adu", "persona:p-amm",
                                                 "persona:p-min"},
             f"{n} {su_disco()} {arch.chiavi_correnti()}")
    # La tenuta: quella della conservazione (turn_log_days), non un numero suo
    cfg_a = Config()
    cfg_a.conversazioni_db = str(tmp / "tenuta.db")
    cfg_a.conversazioni_embedding = ""
    a60 = load_conversazioni(cfg_a, log=lambda m: None, avvia=False,
                             conserva=cons.conversazioni_su_disco)
    verifica("tenuta: turn_log_days (60), niente conversazioni_giorni",
             a60.giorni == cfg_a.turn_log_days == 60
             and not hasattr(cfg_a, "conversazioni_giorni"))
    a60.close()
    for giorni_fa, testo in ((61, "conversazione di sessantuno giorni fa"),
                             (59, "conversazione di cinquantanove giorni fa")):
        cv = Conversazione("persona:p-adu")
        cv.owner, cv.inizio = "p-adu", time.time() - giorni_fa * 86400
        arch.archivia(cv, turni_conv([{"role": "user", "content": testo}],
                                     quando=time.time() - giorni_fa * 86400),
                      "p-adu", "Ginevra", False)
        arch.chiudi(cv, "fine")
        arch.db.execute("UPDATE conversazioni SET fine = ? WHERE id = ?",
                        (time.time() - giorni_fa * 86400, cv.id_archivio))
    arch.db.commit()
    arch._pulizia()
    verifica("scadenza: via la conversazione di 61 giorni fa, resta quella di 59",
             "sessantuno" not in parole_su_disco() and "cinquantanove" in parole_su_disco())
    st = cons.stato()
    verifica("riepilogo: le conversazioni archiviate contate", st["conversazioni"] == 5
             and st["conversazioni_turni"] >= 4
             and "conversazioni archiviate" in C.testo_stato(st), str(st))
    # Svuotare: una persona (anche nella sessione), poi tutto
    r = cons.svuota("p-min", "Leo")
    verifica("svuota un minore: le sue conversazioni su disco",
             r["conversazioni"] == 2 and not arch.chat("p-min")
             and ("p-min", 0) not in su_disco()
             and "persona:p-min" not in arch.chiavi_correnti(), str(r))
    r = cons.svuota("p-adu", "Ginevra")
    verifica("svuota una persona: le sue conversazioni archiviate e quella in corso",
             r["conversazioni"] == 2 and ("p-adu", 0) not in su_disco()
             and arch.chiavi_correnti() == ["persona:p-amm"], str(r))
    verifica("svuota una persona, contrario: quelle di chi amministra restano",
             ("p-amm", 0) in su_disco())
    r = cons.svuota()
    verifica("svuota tutto: archivio vuoto, anche le conversazioni in corso",
             r["conversazioni"] == 1 and arch.conteggi()["conversazioni"] == 0
             and arch.chiavi_correnti() == [] and arch.db.execute(
                 "SELECT COUNT(*) FROM turni_fts").fetchone()[0] == 0, str(r))
    # Dopo lo svuotamento la conversazione che continua apre una riga nuova (niente orfani)
    cx = Conversazione("persona:p-amm")
    cx.id_archivio = 999
    archivia("p-amm", "una conversazione con la riga tolta", conv=cx)
    verifica("riga tolta mentre la conversazione continua: una riga nuova, niente orfani",
             cx.id_archivio != 999 and arch.db.execute(
                 "SELECT COUNT(*) FROM turni WHERE conv NOT IN (SELECT id FROM conversazioni)"
             ).fetchone()[0] == 0)
    cons.conversazioni = None
    arch.close()

    # ───────── esercizi e richieste ai tutori (12/10 sera) ─────────
    # La stessa tenuta di turni e voce (turn_log_days), alla prima rotazione anche quelli di
    # prima; svuotati con la persona e con tutto
    from calliope.esercizi.registro import Registro as RegistroEsercizi
    from calliope.minori import Richieste
    RegistroEsercizi(cfg.memory_db).db.close()
    Richieste(cfg.memory_db, cfg, log=lambda m: None).db.close()
    import sqlite3

    def riempi():
        db = sqlite3.connect(cfg.memory_db)
        db.execute("DELETE FROM esercizi_tentativi")
        db.execute("DELETE FROM richieste_tutori")
        db.execute("DELETE FROM esercizi_segnalazioni")
        for chi in ("p-min", "p-min2"):
            for fa in (59, 60, 61):
                g = datetime.date.today() - datetime.timedelta(days=fa)
                db.execute("INSERT INTO esercizi_tentativi (persona, giorno, quando, materia, "
                           "argomento, esercizio, domanda, attesa, data, esito) VALUES "
                           "(?, ?, ?, 'matematica', 'tabelline', 'f', '7 per 8', '56', '54', "
                           "'sbagliata')", (chi, g.isoformat(), f"{g.isoformat()}T10:00:00"))
                db.execute("INSERT INTO richieste_tutori (minore, tipo, oggetto, creata, "
                           "creata_ts) VALUES (?, 'gioco', 'il gioco dei pirati', ?, ?)",
                           (chi, f"{g.isoformat()}T10:00:00", time.time() - fa * 86400))
                db.execute("INSERT INTO esercizi_segnalazioni (persona, quando, esercizio, "
                           "nota) VALUES (?, ?, 'f', 'secondo me è sbagliato')",
                           (chi, f"{g.isoformat()}T10:00:00"))
        db.commit()
        db.close()

    def righe(chi=None):
        db = sqlite3.connect(cfg.memory_db)
        out = []
        for tabella, col, quando in C.TABELLE_MEMORIA:
            q = f"SELECT {quando} FROM {tabella}" + (f" WHERE {col} = ?" if chi else "")
            out += [r[0][:10] for r in db.execute(q, (chi,) if chi else ())]
        db.close()
        return out

    riempi()
    giorno = {fa: (datetime.date.today() - datetime.timedelta(days=fa)).isoformat()
              for fa in (59, 60, 61)}
    r = cons.ruota()
    rimaste = righe()
    verifica("rotazione: esercizi, segnalazioni e richieste di 61 giorni fa via, 59 e 60 restano",
             giorno[61] not in rimaste and rimaste.count(giorno[59]) == 6
             and rimaste.count(giorno[60]) == 6 and r.get("memoria") == 6, f"{r} {rimaste}")
    cons.giorni = 30
    verifica("tenuta: è turn_log_days (con 30 via anche quelli di 59 giorni)",
             cons.ruota().get("memoria") == 12 and righe() == [])
    cons.giorni = 60
    riempi()
    r = cons.svuota("p-min", "Leo")
    verifica("svuota una persona: anche i suoi esercizi e le sue richieste ai tutori",
             r["esercizi_richieste"] == 9 and righe("p-min") == [] and len(righe("p-min2")) == 9,
             str(r))
    verifica("svuota, contrario: quelli degli altri restano", len(righe("p-min2")) == 9)
    r = cons.svuota()
    verifica("svuota tutto: anche esercizi e richieste", r["esercizi_richieste"] == 9
             and righe() == [], str(r))
    cfg_senza = SimpleNamespace(memory_db=str(tmp / "non-esiste.db"), turn_log_dir=None,
                                turn_log_days=60)
    verifica("contrario: senza il file della memoria niente errori né file nuovi",
             C.Conservazione(cfg_senza, reg, log=lambda m: None)._memoria(
                 limite=datetime.date.today()) == 0
             and not (tmp / "non-esiste.db").exists())

    # ───────── da terminale ─────────
    cart = tmp / "dati"
    cart.mkdir()
    (cart / "speakers.json").write_text(json.dumps([amm.to_dict(), adulto.to_dict(),
                                                    minore.to_dict()]), encoding="utf-8")
    prima = os.getcwd()
    env = {k: os.environ.get(k) for k in ("CALLIOPE_TURN_LOG", "CALLIOPE_CONVERSAZIONI_DB",
                                          "CALLIOPE_CONFIG", "CALLIOPE_MEMORY_DB")}
    try:
        os.chdir(cart)
        os.environ["CALLIOPE_TURN_LOG"] = str(cart / "registro")
        os.environ["CALLIOPE_CONVERSAZIONI_DB"] = str(cart / "conversazioni.db")
        os.environ["CALLIOPE_CONFIG"] = str(cart / "calliope.yaml")
        os.environ["CALLIOPE_MEMORY_DB"] = str(cart / "memoria.db")
        c2 = C.Conservazione(SimpleNamespace(turn_log_dir=str(cart / "registro"),
                                             turn_log_days=60, conserva_voce=True,
                                             conserva_voce_mb=10), Registro(amm), lambda m: None)
        C._scrivi_privato(c2.voce_dir / "p-amm" / oggi / "1.wav", C.wav_mulaw(audio, sr))
        a_t = ArchivioConversazioni(cart / "conversazioni.db", log=lambda m: None, avvia=False,
                                    sessione=False)
        cv = Conversazione("persona:p-amm")
        cv.owner = "p-amm"
        a_t.archivia(cv, turni_conv([{"role": "user", "content": "una frase di Primo"}]),
                     "p-amm", "Primo", False)
        a_t.close()
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = C.main(["--json"])
        d = json.loads(out.getvalue()[out.getvalue().index("{"):])
        verifica("terminale: conteggi in JSON (anche le conversazioni archiviate)",
                 rc == 0 and d["voce_file"] == 1 and d["conversazioni"] == 1, out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = C.main([])
        verifica("terminale: le conversazioni archiviate nel riepilogo e per persona",
                 rc == 0 and "1 conversazioni archiviate" in out.getvalue()
                 and "conversazioni archiviate 1" in out.getvalue(), out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = C.main(["--svuota", "--persona", "Primo"])
        verifica("terminale: --svuota --persona (anche le conversazioni archiviate)",
                 rc == 0 and not (c2.voce_dir / "p-amm").exists()
                 and C.conta_archivio(SimpleNamespace(conversazioni_db=str(
                     cart / "conversazioni.db")))["conversazioni"] == 0
                 and "1 conversazioni archiviate" in out.getvalue(), out.getvalue())
        # Un minore (16/10, decisione 0031): i suoi dati conservati via come quelli di un adulto
        C._scrivi_privato(c2.voce_dir / "p-min" / oggi / "1.wav", C.wav_mulaw(audio, sr))
        a_t = ArchivioConversazioni(cart / "conversazioni.db", log=lambda m: None, avvia=False,
                                    sessione=False)
        cv = Conversazione("persona:p-min")
        cv.owner = "p-min"
        a_t.archivia(cv, turni_conv([{"role": "user", "content": "una frase di Leo"}]),
                     "p-min", "Leo", False)
        a_t.close()
        (cart / "registro" / f"turni-{oggi}.jsonl").write_text(json.dumps(
            {"inizio": f"{oggi}T09:00:00", "livello": "familiare", "testo": "una frase di Leo",
             "voce": {"nome": "Leo", "id": "p-min", "modo": "voce"}}) + "\n", encoding="utf-8")
        # Gli eventi del minore su disco (nella stessa conversazioni.db) e una sua riga della
        # stanza (stanza.db accanto alla configurazione), con una riga di Primo che deve restare
        d_ev = Disco.file(cart / "conversazioni.db", log=lambda m: None)
        r_ev = Registri(d_ev, log=lambda m: None)
        for chiave in ("persona:p-min", "persona:p-amm"):
            rg_ev = r_ev.della_corsia(chiave)
            rg_ev.apri("persona")
            rg_ev.aggiungi("detto_persona", 1, testo="una frase per gli eventi", canale="voce")
        r_ev.scrivi()
        d_ev.db.close()
        from calliope.stanza.tenuta import Tenuta
        import sqlite3 as _sq
        Tenuta(cart / "stanza.db", 60, log=lambda m: None, avvia=False).chiudi()
        dbs = _sq.connect(cart / "stanza.db")
        for seq, (pid, chi_n) in enumerate((("p-min", "Leo"), ("p-amm", "Primo")), 1):
            cur = dbs.execute(
                "INSERT INTO righe (avvio, sat, seq, inizio, fine, testo, chi, persona, nome, "
                "minore) VALUES ('a', '1', ?, ?, ?, ?, 'persona', ?, ?, ?)",
                (seq, time.time(), time.time(), f"una frase di {chi_n} nella stanza", pid, chi_n,
                 1 if pid == "p-min" else 0))
            dbs.execute("INSERT INTO righe_fts (rowid, testo) VALUES (?, ?)",
                        (cur.lastrowid, f"una frase di {chi_n} nella stanza"))
        dbs.commit()
        dbs.close()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = C.main(["--svuota", "--persona", "Leo"])
        ev_dopo = Disco.file(cart / "conversazioni.db", log=lambda m: None)
        chiavi_dopo = set(ev_dopo.chiavi())
        ev_dopo.db.close()
        dbs = _sq.connect(cart / "stanza.db")
        stanza_dopo = [x[0] for x in dbs.execute("SELECT persona FROM righe")]
        dbs.close()
        verifica("terminale: --svuota --persona di un minore (voce, conversazioni, turni, "
                 "eventi, stanza)",
                 rc == 0 and not (c2.voce_dir / "p-min").exists()
                 and C.conta_archivio(SimpleNamespace(conversazioni_db=str(
                     cart / "conversazioni.db")), "p-min")["conversazioni"] == 0
                 and "una frase di Leo" not in (cart / "registro" / f"turni-{oggi}.jsonl")
                 .read_text(encoding="utf-8")
                 and "persona:p-min" not in chiavi_dopo and "p-min" not in stanza_dopo,
                 f"{out.getvalue()} {chiavi_dopo} {stanza_dopo}")
        verifica("terminale, contrario: gli eventi e la stanza di Primo restano",
                 "persona:p-amm" in chiavi_dopo and stanza_dopo == ["p-amm"],
                 f"{chiavi_dopo} {stanza_dopo}")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            C.main([])
        verifica("terminale: il minore nel riepilogo, la voce sì decisa dai tutori",
                 "Leo: minore, voce sì (lo decidono i tutori)" in out.getvalue(), out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            rc = C.main(["--svuota", "--persona", "Nessuno"])
        verifica("terminale, contrario: persona sconosciuta → 1", rc == 1)
    finally:
        os.chdir(prima)
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
