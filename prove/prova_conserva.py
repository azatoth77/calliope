import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della conservazione dei dati (12/10/2026, calliope/conserva.py, decisione 0028 T1).

- `decidi`, il solo posto: adulto riconosciuto sì; minore, ospite, dubbio con un minore, zona
  grigia no (testo); la voce solo sopra soglia, senza compagnia, con il consenso (chi amministra
  sì finché non dice no, gli altri adulti solo dopo il loro «sì»), mai con `conserva_voce: false`;
- registro dei turni: le parole restano solo per gli adulti; minori (dal profilo o dalla fascia),
  ospiti, voci incerte, zona grigia senza parole (restano i numeri e quante parole);
- voce: μ-law che si rilegge (errore piccolo), un file per frase nella cartella della persona,
  permessi 600/700 fuori da Windows; mai per minore, ospite, adulto senza consenso, scritto,
  frase ignorata, compagnia;
- consenso: il «sì» salvato nel profilo; la revoca cancella le registrazioni;
- rotazione: giorni vecchi, persone senza più il diritto, tetto di spazio;
- il registro dei turni di prima ripulito una volta (segno nella cartella);
- svuotare: una persona (voce, parole nei turni, eventi) e tutto;
- eventi: i registri di minori e ospiti non vanno su disco né si riprendono; la rotazione toglie
  quelli rimasti; le parole di un turno incerto restano solo in memoria (`senza_parole`);
  `dati_del_turno` su disco con nomi e lunghezze;
- il tool `dati_conservati`: ospite, minore, scritto, zona grigia rifiutati; domanda e «sì»;
  revoca; «svuota» solo per chi amministra, con la domanda;
- da terminale: `python -m calliope.conserva` (conteggi) e `--svuota --persona`.

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
                         nascita=f"{oggi.year - 10}-01-15")
    return amm, adulto, minore


tmp = Path(tempfile.mkdtemp(prefix="calliope-conserva-"))
try:
    amm, adulto, minore = profili()
    reg = Registro(amm, adulto, minore)

    # ───────── decidi ─────────
    verifica("adulto dalla voce: testo sì", C.decidi(adulto, "testo", "voce").ok)
    verifica("adulto, frase breve: testo sì", C.decidi(adulto, "testo", "breve").ok)
    verifica("contrario: minore, mai (testo, voce, eventi)",
             not any(C.decidi(minore, c, "voce") for c in C.COSE)
             and C.decidi(minore, "voce", "voce").motivo == "minore")
    verifica("contrario: ospite, mai", not any(C.decidi(None, c, "voce") for c in C.COSE))
    verifica("contrario: dubbio con un minore (incerta, minore_vicino): testo no",
             not C.decidi(amm, "testo", "voce", {"incerta"})
             and not C.decidi(amm, "testo", "voce", {"minore_vicino"})
             and C.decidi(amm, "testo", "voce", {"incerta"}).motivo == "dubbio_minore")
    verifica("contrario: zona grigia («conversazione») e proprietario incerto: testo no",
             not C.decidi(amm, "testo", "conversazione")
             and not C.decidi(amm, "testo", "proprietario")
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
    cfg.turn_log_days = 60
    cfg.conserva_voce, cfg.conserva_voce_mb = True, 2000
    cons = C.Conservazione(cfg, reg, log=lambda m: None)
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
            "incerta": turno("Primo", livello="amministra",
                             voce={"incerta": ["Primo", "Leo"]}),
            "grigia": turno("Ginevra", modo="conversazione")}
    for k, r in casi.items():
        r["caso"] = k
        cons.al_turno(r)
        log.write(r)
    righe = {r["caso"]: r for r in (json.loads(x) for x in (
        Path(cfg.turn_log_dir) / f"turni-{oggi}.jsonl").read_text(encoding="utf-8").splitlines())}
    verifica("registro: l'adulto con le parole e gli argomenti",
             righe["adulto"]["testo"] == "accendi la luce della cucina"
             and righe["adulto"]["tool"][0].get("argomenti"))
    for k in ("minore", "minore_fascia", "ospite", "incerta", "grigia"):
        r = righe[k]
        verifica(f"registro, contrario «{k}»: niente parole, restano i numeri",
                 r["testo"] is None and r["risposta"] is None and r.get("testo_parole") == 5
                 and "argomenti" not in r["tool"][0] and r["tool"][0]["nome"] == "casa_comando",
                 str(r)[:300])
    verifica("il ciclo segna il motivo nel turno (letto dall'ombra degli eventi)",
             righe["minore"]["conserva"] == {"testo": False, "motivo": "minore"}
             and "conserva" not in righe["adulto"])
    # Righe scritte da altri (cassetto, schermi) senza il segno: decide la conservazione
    log.write({"inizio": f"{oggi}T11:00:00", "livello": "familiare", "testo": "foto.jpg",
               "voce": {"nome": "Leo", "modo": "schermo"}, "caso": "altri"})
    r = [json.loads(x) for x in (Path(cfg.turn_log_dir) / f"turni-{oggi}.jsonl").read_text(
        encoding="utf-8").splitlines()][-1]
    verifica("contrario: una riga di altri senza segno, di un minore → senza parole",
             r["testo"] is None, str(r))

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
    for nome, r in (("minore", turno("Leo")),
                    ("ospite", turno(None, livello="ospite")),
                    ("adulto senza consenso", turno("Ginevra")),
                    ("frase breve", turno("Primo", modo="breve")),
                    ("compagnia", turno("Primo", voce={"compagnia": {"voci": 2}})),
                    ("scritta", turno("Primo", modo="schermo", canale="scritto")),
                    ("ignorata", {**turno("Primo"), "esito": "ignorato"}),
                    ("incerta con un minore", turno("Primo", voce={"minore_vicino": "Leo"}))):
        if nome == "adulto senza consenso":
            adulto.voce_conservata = None
        cons.al_turno(r, audio, sr)
        verifica(f"voce, contrario «{nome}»: non salvata", not r.get("voce_file"), str(r)[:200])
        adulto.voce_conservata = True
    verifica("nessun file per il minore", not (cons.voce_dir / "p-min").exists())

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
         "voce": {"nome": "Primo", "modo": "voce"}, "risposta": "Sono le nove."})) + "\nrotta{\n",
        encoding="utf-8")
    r = cons.ripulisci_registro()
    righe = vecchia.read_text(encoding="utf-8").splitlines()
    verifica("registro di prima: le parole del minore tolte, l'adulto e la riga rotta restano",
             r and r["turni"] >= 1 and json.loads(righe[0])["testo"] is None
             and json.loads(righe[1])["testo"] == "che ore sono" and righe[2] == "rotta{",
             str(righe)[:300])
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
    verifica("eventi: su disco solo l'adulto; minore, ospite e profilo ignoto in memoria",
             chiavi == {"persona:p-adu"} and regs.della_corsia("persona:p-min").eventi(),
             str(chiavi))
    # Righe di un minore scritte da una versione di prima: la rotazione le toglie
    vecchie = Registri(disco, log=lambda m: None)            # senza conservazione, come prima
    v = vecchie.della_corsia("persona:p-min")
    v.apri("persona")
    v.aggiungi("detto_persona", 1, testo="frase di un ragazzo", canale="voce")
    vecchie.scrivi()
    verifica("(prima) il minore era su disco", "persona:p-min" in disco.chiavi())
    rip = Registri(disco, log=lambda m: None, conserva=cons.registro_su_disco).riprendi()
    verifica("riavvio: il registro del minore non si riprende dal disco", rip["ripresi"] == 1,
             str(rip))
    disco.ruota(60, effimero=lambda k: not cons.registro_su_disco(k))
    verifica("rotazione: via le righe del minore, l'adulto resta",
             set(disco.chiavi()) == {"persona:p-adu"}, str(disco.chiavi()))
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
             and minore.voce_conservata is None)
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

    # ───────── da terminale ─────────
    cart = tmp / "dati"
    cart.mkdir()
    (cart / "speakers.json").write_text(json.dumps([amm.to_dict(), adulto.to_dict()]),
                                        encoding="utf-8")
    prima = os.getcwd()
    env = {k: os.environ.get(k) for k in ("CALLIOPE_TURN_LOG", "CALLIOPE_CONVERSAZIONI_DB",
                                          "CALLIOPE_CONFIG")}
    try:
        os.chdir(cart)
        os.environ["CALLIOPE_TURN_LOG"] = str(cart / "registro")
        os.environ["CALLIOPE_CONVERSAZIONI_DB"] = str(cart / "conversazioni.db")
        os.environ["CALLIOPE_CONFIG"] = str(cart / "calliope.yaml")
        c2 = C.Conservazione(SimpleNamespace(turn_log_dir=str(cart / "registro"),
                                             turn_log_days=60, conserva_voce=True,
                                             conserva_voce_mb=10), Registro(amm), lambda m: None)
        C._scrivi_privato(c2.voce_dir / "p-amm" / oggi / "1.wav", C.wav_mulaw(audio, sr))
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = C.main(["--json"])
        d = json.loads(out.getvalue()[out.getvalue().index("{"):])
        verifica("terminale: conteggi in JSON", rc == 0 and d["voce_file"] == 1, out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = C.main(["--svuota", "--persona", "Primo"])
        verifica("terminale: --svuota --persona", rc == 0 and not (c2.voce_dir / "p-amm").exists(),
                 out.getvalue())
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
